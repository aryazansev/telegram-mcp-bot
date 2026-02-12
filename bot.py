import os
import asyncio
import logging
from aiohttp import web
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

user_conversations = {}

application = None
bot_instance = None


class TelegramMCPBot:
    def __init__(self):
        self.mcp_manager = MCPManager()
        self.ai_handler = AIHandler(os.getenv("OPENROUTER_API_KEY"))
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

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user_id = update.effective_user.id

        welcome_text = """
🤖 Привет! Я умный бот с интеграцией MCP серверов.

📦 Яндекс Доставка - расчёт стоимости и создание заказов
🚚 СДЭК - отслеживание и тарифы
📋 RetailCRM - управление заказами

Просто напишите ваш вопрос!
        """

        await update.message.reply_text(welcome_text)
        user_conversations[user_id] = []

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """
/start - Начать разговор
/help - Показать помощь
/status - Статус MCP серверов
/clear - Очистить историю

Примеры:
• "Рассчитай доставку Яндексом из Москвы в СПб, 2 кг"
• "Отследи СДЭК заказ 1234567890"
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
            status_lines.append(f"   {status}, {tools} инстр.")
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
            user_conversations[user_id] = conversation[-10:]

            await update.message.reply_text(response_text or "Не удалось получить ответ")

        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def webhook_handler(request):
    """Обработка webhook запросов от Telegram"""
    try:
        global application
        if application:
            data = await request.json()
            update = Update.de_json(data, application.bot)
            await application.update_queue.put(update)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    return web.Response(status=200)


async def health_handler(request):
    """Health check"""
    return web.Response(text="OK", status=200)


async def setup_bot() -> Application:
    """Настройка бота"""
    global application, bot_instance

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

    webhook_url = os.getenv('WEBHOOK_URL')
    if webhook_url:
        try:
            await application.bot.set_webhook(
                url=f"{webhook_url}/{os.getenv('TELEGRAM_BOT_TOKEN')}/webhook",
                allowed_updates=Update.ALL_TYPES
            )
            logger.info(f"🔗 Webhook установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"Ошибка webhook: {e}")

    return application


async def run_app():
    """Запуск приложения"""
    global application

    application = await setup_bot()

    # Создаём aiohttp приложение
    app = web.Application()
    app.router.add_post(f"/{os.getenv('TELEGRAM_BOT_TOKEN')}/webhook", webhook_handler)
    app.router.add_get("/health", health_handler)

    # Запускаем веб-сервер
    port = int(os.getenv('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    logger.info(f"🚀 Сервер запущен на порту {port}")

    # Держим приложение запущенным
    while True:
        await asyncio.sleep(3600)


def main():
    """Точка входа"""
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")


if __name__ == '__main__':
    main()
