# Бэкенд для интеграции с ЮMoney

Бэкенд на Flask для обработки OAuth 2.0 авторизации и webhook-уведомлений от ЮMoney.

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Создайте файл `.env` на основе `.env.example`:
```bash
cp .env.example .env
```

3. Заполните переменные окружения в `.env`:
- `YMONEY_CLIENT_ID` - ID приложения ЮMoney
- `YMONEY_CLIENT_SECRET` - Секретный ключ приложения ЮMoney
- `YMONEY_WALLET_NUMBER` - Номер кошелька ЮMoney
- `YMONEY_REDIRECT_URI` - URL для редиректа после авторизации
- `TELEGRAM_BOT_TOKEN` - Токен Telegram бота

## Запуск

```bash
python app.py
```

Сервер запустится на порту 5000 (или на порту, указанном в переменной окружения `PORT`).

## API Endpoints

### 1. `/auth` (GET)
Инициация авторизации OAuth 2.0. Перенаправляет пользователя на страницу авторизации ЮMoney.

### 2. `/yoomoney_redirect` (GET)
Обработчик редиректа после авторизации. Обменивает код на access_token и сохраняет его в БД.

**Параметры:**
- `code` - код авторизации от ЮMoney

### 3. `/yoomoney_webhook` (POST)
Обработчик webhook-уведомлений от ЮMoney о платежах.

**Формат данных:**
```json
{
  "operation_id": "123456789",
  "label": "tg_user_123456789_1234567890",
  "amount": "100.00",
  "status": "success"
}
```

### 4. `/generate_payment` (POST)
API endpoint для генерации платежного URI.

**Запрос:**
```json
{
  "telegram_id": 123456789,
  "amount": 100.00
}
```

**Ответ:**
```json
{
  "payment_uri": "https://yoomoney.ru/transfer/quickpay?requestId=..."
}
```

### 5. `/health` (GET)
Проверка работоспособности сервера.

## База данных

Используется SQLite база данных (`db.sqlite`).

### Таблица `config`
Хранит токены и конфигурацию:
- `key` (TEXT, UNIQUE) - ключ (например, 'access_token')
- `value` (TEXT) - значение

### Таблица `donations`
Хранит данные о донатах:
- `id` (INTEGER, PRIMARY KEY)
- `label` (TEXT, UNIQUE) - уникальная метка платежа
- `telegram_id` (INTEGER) - ID пользователя Telegram
- `amount` (REAL) - сумма доната
- `status` (TEXT) - статус платежа
- `operation_id` (TEXT) - ID операции ЮMoney
- `timestamp` (DATETIME) - время получения уведомления

## Использование в Telegram боте

### Генерация платежной ссылки:

```python
import requests

def generate_payment_link(telegram_id, amount):
    response = requests.post(
        'http://your-backend-url:5000/generate_payment',
        json={
            'telegram_id': telegram_id,
            'amount': amount
        }
    )
    if response.status_code == 200:
        return response.json()['payment_uri']
    return None
```

## Настройка в ЮMoney

1. Зарегистрируйте приложение в [ЮMoney Developer](https://yoomoney.ru/docs/payment-buttons/using-api/oauth)
2. Укажите Redirect URI: `http://your-domain.com:5000/yoomoney_redirect`
3. Укажите Notification URI: `http://your-domain.com:5000/yoomoney_webhook`
4. Получите `CLIENT_ID` и `CLIENT_SECRET`

## Порядок работы

1. Пользователь переходит на `/auth` для авторизации
2. После авторизации ЮMoney перенаправляет на `/yoomoney_redirect`
3. Бэкенд обменивает код на токен и сохраняет его
4. Бот генерирует платежную ссылку через `/generate_payment`
5. После оплаты ЮMoney отправляет webhook на `/yoomoney_webhook`
6. Бэкенд сохраняет данные о платеже в БД

