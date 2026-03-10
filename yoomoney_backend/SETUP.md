# Быстрый старт

## 1. Установка зависимостей

```bash
cd yoomoney_backend
pip install -r requirements.txt
```

## 2. Настройка переменных окружения

Создайте файл `.env`:

```bash
cp .env.example .env
```

Заполните необходимые переменные:
- `YMONEY_CLIENT_ID` - получите в [ЮMoney Developer](https://yoomoney.ru/docs/payment-buttons/using-api/oauth)
- `YMONEY_CLIENT_SECRET` - получите там же
- `YMONEY_WALLET_NUMBER` - номер вашего кошелька ЮMoney
- `YMONEY_REDIRECT_URI` - URL вашего сервера + `/yoomoney_redirect`
- `TELEGRAM_BOT_TOKEN` - токен вашего Telegram бота

## 3. Запуск

```bash
python app.py
```

## 4. Первая авторизация

Откройте в браузере: `http://your-server:5000/auth`

После успешной авторизации токен будет сохранен в БД.

## 5. Использование в Telegram боте

```python
import requests

# Генерация платежной ссылки
def create_payment_link(telegram_id, amount):
    response = requests.post(
        'http://your-backend:5000/generate_payment',
        json={'telegram_id': telegram_id, 'amount': amount}
    )
    if response.status_code == 200:
        return response.json()['payment_uri']
    return None

# Использование
payment_url = create_payment_link(123456789, 100.00)
# Отправьте payment_url пользователю в Telegram
```

## 6. Настройка webhook в ЮMoney

В настройках приложения ЮMoney укажите:
- **Notification URI**: `http://your-server:5000/yoomoney_webhook`

После этого все платежи будут автоматически сохраняться в БД.

