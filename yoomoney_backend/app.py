"""
Бэкенд для интеграции с ЮMoney (OAuth 2.0 и Webhooks)
"""
import os
import sqlite3
import requests
import logging
from datetime import datetime
from flask import Flask, request, redirect, jsonify
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Конфигурация из переменных окружения
CLIENT_ID = os.getenv('YMONEY_CLIENT_ID', '')
CLIENT_SECRET = os.getenv('YMONEY_CLIENT_SECRET', '')
WALLET_NUMBER = os.getenv('YMONEY_WALLET_NUMBER', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
REDIRECT_URI = os.getenv('YMONEY_REDIRECT_URI', 'http://localhost:5000/yoomoney_redirect')
WEBHOOK_SECRET = os.getenv('YMONEY_WEBHOOK_SECRET', '')

# Путь к базе данных
DB_PATH = os.getenv('DB_PATH', 'db.sqlite')

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица для хранения токенов и конфигурации
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL
        )
    ''')
    
    # Таблица для хранения данных о донатах
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT UNIQUE NOT NULL,
            telegram_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            operation_id TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

def get_config_value(key):
    """Получить значение из таблицы config"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM config WHERE key = ?', (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def set_config_value(key, value):
    """Установить значение в таблице config"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO config (key, value) 
        VALUES (?, ?)
    ''', (key, value))
    conn.commit()
    conn.close()
    logger.info(f"Конфигурация обновлена: {key}")

def save_donation(label, telegram_id, amount, operation_id=None, status='pending'):
    """Сохранить данные о донате"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO donations 
            (label, telegram_id, amount, status, operation_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (label, telegram_id, amount, status, operation_id, datetime.now()))
        conn.commit()
        logger.info(f"Донат сохранен: label={label}, amount={amount}, telegram_id={telegram_id}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Донат с label={label} уже существует")
        return False
    finally:
        conn.close()

@app.route('/auth', methods=['GET'])
def auth():
    """Страница инициации авторизации"""
    if not CLIENT_ID:
        return jsonify({'error': 'CLIENT_ID не настроен'}), 500
    
    # Параметры для авторизации
    auth_url = 'https://yoomoney.ru/oauth/authorize'
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'scope': 'operation-history payment-p2p',
        'redirect_uri': REDIRECT_URI
    }
    
    # Формируем URL с параметрами
    auth_url_with_params = f"{auth_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
    
    logger.info(f"Перенаправление на авторизацию: {auth_url_with_params}")
    return redirect(auth_url_with_params)

SUCCESS_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Авторизация успешна - MOROZ VPN</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }}
        .success-icon {{
            width: 80px;
            height: 80px;
            background: #27ae60;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            font-size: 40px;
        }}
        h1 {{
            color: #2c3e50;
            margin-bottom: 15px;
            font-size: 28px;
        }}
        p {{
            color: #7f8c8d;
            line-height: 1.6;
            margin-bottom: 20px;
        }}
        .btn {{
            display: inline-block;
            padding: 12px 30px;
            background: #3498db;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            margin-top: 10px;
            transition: background 0.3s;
        }}
        .btn:hover {{
            background: #2980b9;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✓</div>
        <h1>Авторизация успешна!</h1>
        <p>Ваш аккаунт ЮMoney успешно подключен к системе MOROZ VPN.</p>
        <p>Теперь вы можете использовать все возможности бота.</p>
        <p style="margin-top: 30px; font-size: 14px; color: #95a5a6;">
            Вы можете закрыть эту страницу и вернуться в Telegram бот.
        </p>
    </div>
</body>
</html>
"""

ERROR_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ошибка авторизации - MOROZ VPN</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }}
        .error-icon {{
            width: 80px;
            height: 80px;
            background: #e74c3c;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            font-size: 40px;
        }}
        h1 {{
            color: #2c3e50;
            margin-bottom: 15px;
            font-size: 28px;
        }}
        p {{
            color: #7f8c8d;
            line-height: 1.6;
            margin-bottom: 20px;
        }}
        .error-details {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            color: #e74c3c;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error-icon">✗</div>
        <h1>Ошибка авторизации</h1>
        <p>К сожалению, не удалось завершить авторизацию.</p>
        <div class="error-details">
            {{error_message}}
        </div>
        <p style="margin-top: 20px; font-size: 14px; color: #95a5a6;">
            Попробуйте еще раз или обратитесь в поддержку.
        </p>
    </div>
</body>
</html>
"""

@app.route('/yoomoney_redirect', methods=['GET'])
def yoomoney_redirect():
    """Обработчик токена (Redirect URI)"""
    code = request.args.get('code')
    error = request.args.get('error')
    error_description = request.args.get('error_description', '')
    
    if error:
        logger.error(f"Ошибка авторизации: {error} - {error_description}")
        error_message = error_description if error_description else f"Ошибка: {error}"
        return ERROR_PAGE.format(error_message=error_message), 400
    
    if not code:
        return ERROR_PAGE.format(error_message="Код авторизации не получен"), 400
    
    # Обмениваем код на токен
    token_url = 'https://yoomoney.ru/oauth/token'
    data = {
        'code': code,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI
    }
    
    try:
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        token_data = response.json()
        
        access_token = token_data.get('access_token')
        if not access_token:
            logger.error(f"Токен не получен: {token_data}")
            return ERROR_PAGE.format(error_message="Токен не получен от ЮMoney"), 500
        
        # Сохраняем токен в базу данных
        set_config_value('access_token', access_token)
        logger.info("Токен успешно сохранен")
        
        return SUCCESS_PAGE, 200
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при получении токена: {e}")
        return ERROR_PAGE.format(error_message=f"Ошибка при получении токена: {str(e)}"), 500

PAYMENT_SUCCESS_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Платеж успешен - MOROZ VPN</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }}
        .success-icon {{
            width: 80px;
            height: 80px;
            background: #27ae60;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            font-size: 40px;
        }}
        h1 {{
            color: #2c3e50;
            margin-bottom: 15px;
            font-size: 28px;
        }}
        p {{
            color: #7f8c8d;
            line-height: 1.6;
            margin-bottom: 20px;
        }}
        .amount {{
            font-size: 36px;
            font-weight: bold;
            color: #27ae60;
            margin: 20px 0;
        }}
        .info {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            font-size: 14px;
            color: #7f8c8d;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✓</div>
        <h1>Платеж успешно выполнен!</h1>
        <div class="amount">{amount} ₽</div>
        <p>Спасибо за ваш платеж!</p>
        <div class="info">
            <p>Ваш платеж обработан и зачислен на счет.</p>
            <p>Вернитесь в Telegram бот для продолжения работы.</p>
        </div>
    </div>
</body>
</html>
"""

@app.route('/yoomoney_webhook', methods=['POST'])
def yoomoney_webhook():
    """Обработчик уведомлений (Notification URI)"""
    try:
        data = request.get_json()
        
        if not data:
            logger.warning("Пустой запрос от webhook")
            return jsonify({'error': 'Пустой запрос'}), 400
        
        # Извлекаем данные о платеже
        operation_id = data.get('operation_id')
        label = data.get('label')
        amount = data.get('amount')
        status = data.get('status', 'pending')
        
        if not label:
            logger.warning("Label не найден в уведомлении")
            return jsonify({'error': 'Label не найден'}), 400
        
        # Парсим telegram_id из label (формат: tg_user_ID_...)
        telegram_id = None
        if label.startswith('tg_user_'):
            try:
                # Извлекаем ID из label (например, tg_user_123456789 -> 123456789)
                parts = label.split('_')
                if len(parts) >= 3:
                    telegram_id = int(parts[2])
            except (ValueError, IndexError) as e:
                logger.error(f"Ошибка парсинга telegram_id из label {label}: {e}")
        
        if not telegram_id:
            logger.warning(f"Не удалось извлечь telegram_id из label: {label}")
            return jsonify({'error': 'Неверный формат label'}), 400
        
        if not amount:
            logger.warning("Amount не найден в уведомлении")
            return jsonify({'error': 'Amount не найден'}), 400
        
        # Сохраняем данные о платеже
        save_donation(
            label=label,
            telegram_id=telegram_id,
            amount=float(amount),
            operation_id=operation_id,
            status=status
        )
        
        logger.info(f"Уведомление обработано: label={label}, amount={amount}, telegram_id={telegram_id}")
        
        # Возвращаем 200 OK для подтверждения получения
        return jsonify({'status': 'ok'}), 200
        
    except Exception as e:
        logger.error(f"Ошибка при обработке webhook: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/payment_success', methods=['GET'])
def payment_success_page():
    """Страница успешного платежа (для редиректа после оплаты)"""
    amount = request.args.get('amount', '')
    return PAYMENT_SUCCESS_PAGE.format(amount=amount), 200

def generate_payment_uri(telegram_id, amount=None):
    """
    Генерирует платежный URI для P2P-перевода
    
    Args:
        telegram_id: ID пользователя Telegram
        amount: Сумма платежа (опционально)
    
    Returns:
        str: Платежный URL или None в случае ошибки
    """
    access_token = get_config_value('access_token')
    
    if not access_token:
        logger.error("Access token не найден. Необходима авторизация.")
        return None
    
    if not WALLET_NUMBER:
        logger.error("Номер кошелька не настроен")
        return None
    
    # Генерируем уникальный label
    label = f"tg_user_{telegram_id}_{int(datetime.now().timestamp())}"
    
    # URL для создания запроса на перевод
    request_payment_url = 'https://yoomoney.ru/api/request-payment'
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        'pattern_id': 'p2p',
        'to': WALLET_NUMBER,
        'label': label
    }
    
    if amount:
        data['amount'] = str(amount)
    
    try:
        response = requests.post(request_payment_url, headers=headers, data=data)
        response.raise_for_status()
        result = response.json()
        
        if result.get('status') == 'success':
            request_id = result.get('request_id')
            if request_id:
                # Формируем платежный URL
                payment_url = f"https://yoomoney.ru/transfer/quickpay?requestId={request_id}"
                logger.info(f"Платежный URI создан: {payment_url} для telegram_id={telegram_id}")
                return payment_url
            else:
                logger.error("request_id не найден в ответе")
                return None
        else:
            error = result.get('error', 'Неизвестная ошибка')
            logger.error(f"Ошибка создания платежа: {error}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при создании платежного URI: {e}")
        return None

@app.route('/generate_payment', methods=['POST'])
def generate_payment():
    """API endpoint для генерации платежного URI"""
    data = request.get_json()
    
    telegram_id = data.get('telegram_id')
    amount = data.get('amount')
    
    if not telegram_id:
        return jsonify({'error': 'telegram_id обязателен'}), 400
    
    payment_uri = generate_payment_uri(telegram_id, amount)
    
    if payment_uri:
        return jsonify({'payment_uri': payment_uri}), 200
    else:
        return jsonify({'error': 'Не удалось создать платежный URI'}), 500

@app.route('/health', methods=['GET'])
def health():
    """Проверка работоспособности"""
    return jsonify({'status': 'ok'}), 200

# Импортируем и инициализируем админ-панель
try:
    from admin import init_admin_routes
    init_admin_routes(app, DB_PATH)
    logger.info("Админ-панель инициализирована: /admin")
except ImportError:
    logger.warning("Модуль admin не найден, админ-панель недоступна")

if __name__ == '__main__':
    # Инициализируем базу данных при запуске
    init_db()
    
    # Запускаем Flask приложение
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Запуск сервера на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)

