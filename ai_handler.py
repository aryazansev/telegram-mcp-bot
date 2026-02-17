import json
from typing import List, Dict, Any
import httpx
import os

from context_manager import ContextManager, estimate_tokens, trim_messages
from memory import memory_store


class AIHandler:
    """Обработчик запросов с использованием OpenRouter через httpx"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1"
        self.model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
        self.context_manager = ContextManager(
            max_tokens=120000,
            max_tool_results_tokens=25000,
            summarize_threshold=100000
        )
    
    def _build_system_prompt(self, user_id: int = None) -> str:
        """Построение system prompt с памятью и примерами"""
        
        # Few-shot примеры
        examples_text = """
Примеры удачных диалогов:
Пользователь: Где мой заказ 132567A?
Ассистент: Сейчас проверю по номеру заказа в RetailCRM...

Пользователь: Хочу кроссовки размера 42
Ассистент: Проверю наличие товара в каталоге...

Пользователь: Сколько стоит доставка до Москвы?
Ассистент: Рассчитаю стоимость доставки СДЭК...
"""
        
        # Память пользователя
        user_facts_text = ""
        if user_id:
            user_facts_text = memory_store.get_facts_text(user_id)
        
        # Базовый промпт
        base_prompt = """Ты - интеллектуальный ассистент для управления бизнесом с полным доступом к RetailCRM, СДЭК и Яндекс Доставке.

🔑 У ТЕБЯ ЕСТЬ ПОЛНЫЙ ДОСТУП ко всем методам API:

📦 RETAILCRM (37 инструментов):
- Полный доступ к заказам: получение списка, поиск по ID/номеру, создание, редактирование
- Клиенты: полный CRUD
- Товары: просмотр каталога, поиск по ID
- Задачи, расходы, справочники

🚚 СДЭК (15 инструментов):
- Расчет стоимости и сроков доставки
- Создание и отслеживание заказов
- Управление ПВЗ

📮 ЯНДЕКС ДОСТАВКА:
- Расчет тарифов, создание и отслеживание доставок

❗️ ВАЖНО:
1. Используй инструменты АКТИВНО для ответов
2. Не говори что нет доступа - у тебя есть полный доступ
3. Формат вызова: server_name__tool_name (retailcrm__get_order_by_number)

Ты помогаешь с заказами, клиентами, доставкой, товарами."""
        
        # Собираем полный промпт
        parts = [base_prompt]
        
        if user_facts_text:
            parts.append(f"\n{user_facts_text}")
        
        parts.append(f"\n{examples_text}")
        
        return "\n\n".join(parts)
    
    async def process_message(
        self, 
        user_message: str, 
        tools: List[Dict],
        conversation_history: List[Dict] = None,
        tool_results: List[Dict] = None,
        user_id: int = None
    ) -> Dict[str, Any]:
        """Обработка сообщения с возможностью вызова инструментов"""
        
        conversation = list(conversation_history) if conversation_history else []
        
        system_content = self._build_system_prompt(user_id)
        
        system_message = {
            "role": "system",
            "content": system_content
        }
        
        full_messages = self.context_manager.prepare_messages(
            conversation,
            system_message=system_message,
            current_message=user_message,
            tool_results=tool_results
        )
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://telegram-mcp-bot.onrender.com",
            "X-Title": "Telegram MCP Bot"
        }
        
        # Convert MCP tools format to OpenAI format
        # Limit tools to avoid token limit (max ~64000 tokens)
        openai_tools = None
        if tools:
            openai_tools = []
            # Prioritize tools: RetailCRM first (orders, customers), then others
            # Sort to put retailcrm tools first
            sorted_tools = sorted(tools, key=lambda t: (0 if t["function"]["name"].startswith("retailcrm") else 1, t["function"]["name"]))
            # Take first 25 tools (increased from 15)
            limited_tools = sorted_tools[:25] if len(sorted_tools) > 25 else sorted_tools
            print(f"Limiting tools from {len(tools)} to {len(limited_tools)} (prioritized RetailCRM)")
            
            for tool in limited_tools:
                # Truncate descriptions to save tokens
                description = tool["function"]["description"]
                if len(description) > 200:
                    description = description[:197] + "..."
                
                openai_tool = {
                    "type": "function",
                    "function": {
                        "name": tool["function"]["name"],
                        "description": description,
                        "parameters": tool["function"].get("parameters") or tool["function"].get("inputSchema", {})
                    }
                }
                openai_tools.append(openai_tool)
        
        data = {
            "model": self.model,
            "messages": full_messages
        }
        
        if openai_tools:
            data["tools"] = openai_tools
            data["tool_choice"] = "auto"
        
        enable_compression = os.getenv("PROMPT_COMPRESSION", "false").lower() == "true"
        if enable_compression:
            data["transforms"] = ["middle-out"]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=60.0
            )
            
            if response.status_code == 400:
                error_text = response.text
                raise Exception(f"OpenRouter API Error: Bad Request (400). Response: {error_text[:500]}")
            elif response.status_code == 401:
                raise Exception("OpenRouter API Error: Invalid API key. Please check your OPENROUTER_API_KEY at https://openrouter.ai/keys")
            elif response.status_code == 429:
                raise Exception("OpenRouter API Error: Rate limit exceeded. Please check your account at https://openrouter.ai/")
            elif response.status_code == 502:
                raise Exception("OpenRouter API Error: Service temporarily unavailable (502 Bad Gateway). Please try again later.")
            
            response.raise_for_status()
            result = response.json()
            
            # Debug: log the full response
            print(f"OpenRouter response: {json.dumps(result, indent=2)[:1000]}")
            
            # Check if response has expected structure
            if "choices" not in result:
                error_msg = f"Unexpected response format. Keys: {list(result.keys())}"
                if "error" in result:
                    error_msg += f" Error: {result['error']}"
                raise Exception(f"OpenRouter API Error: {error_msg}")
            
            if not result["choices"]:
                raise Exception("OpenRouter API Error: Empty choices array")
        
        choice = result["choices"][0]
        message = choice["message"]
        
        response_data = {
            "content": message.get("content"),
            "tool_calls": None,
            "finish_reason": choice.get("finish_reason")
        }
        
        if "tool_calls" in message and message["tool_calls"]:
            response_data["tool_calls"] = [
                {
                    "name": tc["function"]["name"],
                    "arguments": json.loads(tc["function"]["arguments"]),
                    "id": tc["id"]
                }
                for tc in message["tool_calls"]
            ]
        
        return response_data
