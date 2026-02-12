import json
from typing import List, Dict, Any
import httpx
import os


class AIHandler:
    """Обработчик запросов с использованием OpenRouter через httpx"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1"
        self.model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    
    async def process_message(
        self, 
        user_message: str, 
        tools: List[Dict],
        conversation_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """Обработка сообщения с возможностью вызова инструментов"""
        
        messages = conversation_history or []
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        system_message = {
            "role": "system",
            "content": """Ты умный ассистент для работы с логистикой и CRM.
У тебя есть доступ к трём системам:
1. Яндекс Доставка - расчёт стоимости доставки, создание заказов
2. СДЭК - отслеживание отправлений, расчёт тарифов
3. RetailCRM - управление заказами и клиентами

Используй доступные инструменты для помощи пользователю. 
Если нужно вызвать функцию, используй полное имя в формате: server_name__tool_name"""
        }
        
        full_messages = [system_message] + messages
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://telegram-mcp-bot.onrender.com",
            "X-Title": "Telegram MCP Bot"
        }
        
        # Convert MCP tools format to OpenAI format
        openai_tools = None
        if tools:
            openai_tools = []
            for tool in tools:
                openai_tool = {
                    "type": "function",
                    "function": {
                        "name": tool["function"]["name"],
                        "description": tool["function"]["description"],
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
