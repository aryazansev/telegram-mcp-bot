import os
import asyncio
import logging
from typing import Dict, List
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from mcp_client import MCPManager
from ai_handler import AIHandler

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

user_conversations: Dict[int, List[Dict]] = {}


class TelegramMCPBot:
    def __init__(self):
        self.mcp_manager = MCPManager()
        self.ai_handler = AIHandler(os.getenv('OPENAI_API_KEY'))
        self.application = None
    
    async def initialize(self):
        """Инициализация MCP серверов"""
        self.mcp_manager.add_server(
            'yandex_delivery',
            os.getenv('YANDEX_DELIVERY_MCP_URL')
        )
        self.mcp_manager.add_server(
            'cdek',
            os.getenv('CDEK_MCP_URL')
        )
        self.mcp_manager.add_server(
            'retailcrm',
            os.getenv('RETAILCRM_MCP_URL')
        )
        
        await self.mcp_manager.initialize_all()
        logger.info("Все MCP серверы инициализированы")
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user_id = update.effective_user.id
        
        welcome_text = """
🤖 Привет! Я умный бот с интеграцией MCP серверов.

Я могу помочь вам с:
📦 Яндекс Доставка - расчёт стоимости и создание заказов
🚚 СДЭК - отслеживание и тарифы  
📋 RetailCRM - управление заказами

Просто напишите ваш вопрос или запрос!
        """
        
        await update.message.reply_text(welcome_text)
        user_conversations[user_id] = []
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """
Доступные команды:
/start - Начать разговор
/help - Показать помощь
/clear - Очистить историю

Примеры запросов:
• "Рассчитай доставку Яндексом из Москвы в СПб, 2 кг"
• "Отследи СДЭК заказ 1234567890"
• "Покажи заказы в RetailCRM за сегодня"
        """
        await update.message.reply_text(help_text)
    
    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Очистка истории"""
        user_id = update.effective_user.id
        user_conversations[user_id] = []
        await update.message.reply_text("✅ История очищена")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка сообщений"""
        user_id = update.effective_user.id
        user_message = update.message.text
        
        await update.message.chat.send_action(action="typing")
        
        try:
            conversation = user_conversations.get(user_id, [])
            tools = self.mcp_manager.get_tools_for_llm()
            
            ai_response = await self.ai_handler.process_message(
                user_message,
                tools,
                conversation
            )
            
            if ai_response.get('tool_calls'):
                tool_results = []
                
                for tool_call in ai_response['tool_calls']:
                    result = await self.mcp_manager.execute_tool(
                        tool_call['name'], 
                        tool_call['arguments']
                    )
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call['id'],
                        "content": result
                    })
                
                conversation.append({
                    "role": "assistant",
                    "content": ai_response['content'] or "",
                    "tool_calls": [
                        {
                            "id": tc['id'],
                            "type": "function",
                            "function": {
                                "name": tc['name'],
                                "arguments": str(tc['arguments'])
                            }
                        }
                        for tc in ai_response['tool_calls']
                    ]
                })
                conversation.extend(tool_results)
                
                final_response = await self.ai_handler.process_message(
                    "Обработай результаты и ответь пользователю",
                    [],
                    conversation
                )
                
                response_text = final_response['content']
            else:
                response_text = ai_response['content']
            
            conversation.append({"role": "user", "content": user_message})
            conversation.append({"role": "assistant", "content": response_text})
            user_conversations[user_id] = conversation[-20:]
            
            await update.message.reply_text(response_text or "Не удалось получить ответ")
            
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    def run(self):
        """Запуск бота"""
        self.application = Application.builder().token(
            os.getenv('TELEGRAM_BOT_TOKEN')
        ).build()
        
        self.application.add_handler(CommandHandler('start', self.start))
        self.application.add_handler(CommandHandler('help', self.help_command))
        self.application.add_handler(CommandHandler('clear', self.clear_command))
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        
        asyncio.get_event_loop().run_until_complete(self.initialize())
        
        logger.info("Бот запущен!")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
        
        asyncio.get_event_loop().run_until_complete(
            self.mcp_manager.close_all()
        )


if __name__ == '__main__':
    bot = TelegramMCPBot()
    bot.run()
