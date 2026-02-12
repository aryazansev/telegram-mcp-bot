import os
import asyncio
import logging
from typing import Dict, List
from flask import Flask, request, Response
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
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

user_conversations: Dict[int, List[Dict]] = {}

flask_app = Flask(__name__)

# Глобальные переменные
application = None
bot_instance = None


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

        health_status = []
        for name, server in self.mcp_manager.servers.items():
            status = "✅" if server.is_healthy else "❌"
            tools_count = len(server.tools)
            health_status.append(f"{status} {name}: {tools_count} инструментов")

        logger.info("MCP серверы: " + " | ".join(health_status))

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
/status - Проверить статус MCP серверов
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

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверка статуса MCP серверов"""
        status_lines = ["📊 Статус MCP серверов:\n"]

        for name, server in self.mcp_manager.servers.items():
            is_healthy = await server.check_health()
            status = "✅ Онлайн" if is_healthy else "❌ Недоступен"
            tools = len(server.tools)

            status_lines.append(f"{'🟢' if is_healthy else '🔴'} *{name}*")
            status_lines.append(f"   Статус: {status}")
            status_lines.append(f"   Инструменты: {tools}")
            status_lines.append("")

        status_text = "\n".join(status_lines)
        await update.message.reply_text(status_text, parse_mode='Markdown')

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка сообщений"""
        if not update.message or not update.message.text:
            return

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


@flask_app.route(f"/{os.getenv('TELEGRAM_BOT_TOKEN')}/webhook", methods=['POST'])
async def webhook():
    """Обработка входящих webhook запросов"""
    try:
        global application
        if application:
            await application.update_queue.put(
                Update.de_json(request.get_json(force=True), application.bot)
            )
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    return Response(status=200)


@flask_app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return 'OK'


async def setup_bot():
    """Настройка бота"""
    global bot_instance, application

    bot_instance = TelegramMCPBot()
    await bot_instance.initialize()

    application = Application.builder().token(
        os.getenv('TELEGRAM_BOT_TOKEN')
    ).build()

    application.add_handler(CommandHandler('start', bot_instance.start))
    application.add_handler(CommandHandler('help', bot_instance.help_command))
    application.add_handler(CommandHandler('clear', bot_instance.clear_command))
    application.add_handler(CommandHandler('status', bot_instance.status_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_instance.handle_message)
    )

    await application.initialize()
    await application.start()

    logger.info("🤖 Бот инициализирован!")

    # Устанавливаем webhook
    webhook_url = os.getenv('WEBHOOK_URL')
    if webhook_url:
        await application.bot.set_webhook(
            url=f"{webhook_url}/{os.getenv('TELEGRAM_BOT_TOKEN')}/webhook",
            allowed_updates=Update.ALL_TYPES
        )
        logger.info(f"🔗 Webhook установлен: {webhook_url}")


def run():
    """Запуск"""
    port = int(os.getenv('PORT', 10000))

    # Запускаем асинхронную инициализацию
    asyncio.run(setup_bot())

    # Запускаем Flask
    flask_app.run(host='0.0.0.0', port=port)


if __name__ == '__main__':
    run()
