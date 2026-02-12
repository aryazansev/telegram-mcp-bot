# Telegram MCP Bot

Умный Telegram бот с подключением к MCP серверам (Яндекс Доставка, СДЭК, RetailCRM).

## Развёртывание на Render

### 1. Создайте репозиторий на GitHub

### 2. Загрузите код на GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/telegram-mcp-bot.git
git push -u origin main
```

### 3. Разверните на Render

1. Создайте аккаунт на [Render](https://render.com)
2. Нажмите "New +" → "Web Service"
3. Подключите ваш GitHub репозиторий
4. Настройте:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
5. В секции **Environment Variables** добавьте:
   - `TELEGRAM_BOT_TOKEN`: ваш токен от @BotFather
   - `OPENAI_API_KEY`: ваш ключ от OpenAI
   - `YANDEX_DELIVERY_MCP_URL`: `https://yandex-delivery-mcp.onrender.com`
   - `CDEK_MCP_URL`: `https://cdek-mcp.onrender.com`
   - `RETAILCRM_MCP_URL`: `https://retailcrm-mcp.onrender.com`

### 4. Запуск

После развёртывания бот автоматически запустится и начнёт работу.

## Локальный запуск

```bash
pip install -r requirements.txt
cp .env.example .env
# Отредактируйте .env с вашими токенами
python bot.py
```

## Функционал

- 📦 **Яндекс Доставка** - расчёт стоимости, создание заказов
- 🚚 **СДЭК** - отслеживание, тарифы
- 📋 **RetailCRM** - управление заказами и клиентами

## Требования

- Python 3.10+
- Telegram Bot Token
- OpenAI API Key
