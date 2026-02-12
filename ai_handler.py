import json
from typing import List, Dict, Any
from openai import AsyncOpenAI


class AIHandler:
    """Обработчик запросов с использованием OpenAI"""
    
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"
    
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
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            tools=tools if tools else None,
            tool_choice="auto"
        )
        
        message = response.choices[0].message
        
        result = {
            "content": message.content,
            "tool_calls": None,
            "finish_reason": response.choices[0].finish_reason
        }
        
        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                    "id": tc.id
                }
                for tc in message.tool_calls
            ]
        
        return result
