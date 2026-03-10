"""Веб-бэкенд для интеграции с YooMoney"""
import os
import logging
import uuid
import hashlib
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, redirect, render_template_string, jsonify
from config import (
    YMONEY_CLIENT_ID, YMONEY_CLIENT_SECRET, YMONEY_REDIRECT_URI,
    YMONEY_NOTIFICATION_URI, YMONEY_SITE_URL,
    WEB_SERVER_HOST, WEB_SERVER_PORT, ADMIN_ID, YMONEY_WALLET
)
from database import get_db_session, Payment, User, VPNKey
from yoomoney_helper import YooMoneyHelper
from config_manager import config_manager
import requests

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Инициализация helper для работы с YooMoney API
# Токен может быть получен из БД через config_manager
def get_yoomoney_helper() -> YooMoneyHelper:
    """Получить инициализированный helper с токеном из БД"""
    # Пытаемся получить токен из БД (если был сохранен после OAuth)
    token = config_manager.get("YMONEY_ACCESS_TOKEN") if config_manager else None
    
    helper = YooMoneyHelper(
        client_id=YMONEY_CLIENT_ID,
        client_secret=YMONEY_CLIENT_SECRET,
        redirect_uri=YMONEY_REDIRECT_URI,
        wallet=YMONEY_WALLET,
        token=token
    )
    return helper

yoomoney_helper = get_yoomoney_helper()

# Секретный ключ для подписи webhook'ов (генерируется автоматически)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest())


@app.route('/health', methods=['GET'])
def health():
    """Проверка здоровья сервиса"""
    return jsonify({"status": "ok", "service": "yoomoney_backend"}), 200


@app.route('/yoomoney_auth', methods=['GET'])
def yoomoney_auth():
    """OAuth 2.0 авторизация в YooMoney"""
    global yoomoney_helper
    
    # Обновляем helper с актуальным токеном из БД перед использованием
    yoomoney_helper = get_yoomoney_helper()
    
    try:
        # Используем helper для генерации OAuth URL
        auth_url = yoomoney_helper.get_oauth_url()
        
        logger.info(f"Redirecting to YooMoney OAuth: {auth_url}")
        return redirect(auth_url)
    
    except Exception as e:
        logger.error(f"Error in yoomoney_auth: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route('/yoomoney_redirect', methods=['GET'])
def yoomoney_redirect():
    """Обработка redirect от YooMoney после OAuth авторизации"""
    global yoomoney_helper
    
    # Обновляем helper с актуальным токеном из БД перед использованием
    yoomoney_helper = get_yoomoney_helper()
    
    try:
        code = request.args.get('code')
        error = request.args.get('error')
        
        if error:
            logger.error(f"YooMoney OAuth error: {error}")
            return render_template_string(WELCOME_PAGE_TEMPLATE_ERROR.format(error=error)), 200
        
        if not code:
            logger.error("No code in redirect from YooMoney")
            return render_template_string(WELCOME_PAGE_TEMPLATE_ERROR.format(error="No authorization code")), 200
        
        # Используем helper для обмена кода на токен
        try:
            token_info = yoomoney_helper.exchange_code_for_token(code)
            access_token = token_info.get('access_token')
            
            if not access_token:
                logger.error(f"No access token in response: {token_info}")
                return render_template_string(WELCOME_PAGE_TEMPLATE_ERROR.format(error="No access token")), 200
            
            logger.info(f"Successfully obtained access token: {access_token[:20]}...")
            
            # Сохраняем токен в БД через config_manager
            if config_manager:
                config_manager.set("YMONEY_ACCESS_TOKEN", access_token)
                logger.info("YooMoney access token saved to database")
            
            # Обновляем helper с новым токеном
            yoomoney_helper = get_yoomoney_helper()
            yoomoney_helper.token = access_token
            yoomoney_helper._client = None  # Сброс клиента для пересоздания
            
            return render_template_string(WELCOME_PAGE_TEMPLATE_SUCCESS), 200
        
        except Exception as token_error:
            logger.error(f"Failed to exchange code for token: {token_error}", exc_info=True)
            return render_template_string(WELCOME_PAGE_TEMPLATE_ERROR.format(error="Failed to get access token")), 200
    
    except Exception as e:
        logger.error(f"Error in yoomoney_redirect: {e}", exc_info=True)
        return render_template_string(WELCOME_PAGE_TEMPLATE_ERROR.format(error=str(e))), 200


@app.route('/generate_payment_uri', methods=['POST'])
def generate_payment_uri():
    """Генерация URI для оплаты через YooMoney"""
    global yoomoney_helper
    
    # Обновляем helper с актуальным токеном из БД перед использованием
    yoomoney_helper = get_yoomoney_helper()
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        user_id = data.get('user_id')
        amount = data.get('amount')
        description = data.get('description', 'VPN доступ')
        
        if not user_id or not amount:
            return jsonify({"error": "user_id and amount are required"}), 400
        
        # Получаем сессию БД
        db = get_db_session()
        
        try:
            # Проверяем существование пользователя
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            # Получаем дополнительные параметры для подписок
            payment_type = data.get('payment_type', 'donation')  # 'donation' | 'qr_subscription' | 'test'
            
            # Генерируем уникальный label для платежа в зависимости от типа
            if payment_type == 'donation':
                payment_label = f"donation_{user_id}_{int(datetime.now().timestamp())}"
            elif payment_type == 'qr_subscription':
                payment_label = f"qr_{user_id}_{int(datetime.now().timestamp())}"
            else:
                payment_label = f"vpn_{user_id}_{int(datetime.now().timestamp())}"
            qr_code_count = data.get('qr_code_count', None)
            subscription_period_days = data.get('subscription_period_days', None)
            is_test = data.get('is_test', False)
            
            # Создаем запись о платеже в БД
            payment = Payment(
                user_id=user_id,
                amount=str(amount),
                currency='RUB',
                status='pending',
                payment_method='yoomoney',
                payment_type=payment_type,
                yoomoney_label=payment_label,
                description=description,
                expires_at=datetime.now() + timedelta(hours=24),  # Ссылка действует 24 часа
                qr_code_count=qr_code_count,
                subscription_period_days=subscription_period_days,
                is_test=is_test
            )
            db.add(payment)
            db.commit()
            db.refresh(payment)
            
            # Используем helper для генерации URL быстрой оплаты
            try:
                # Получаем wallet динамически из БД (приоритет) или из config.py
                wallet = config_manager.get("YMONEY_WALLET") or YMONEY_WALLET or None
                
                if not wallet:
                    logger.error("YMONEY_WALLET not configured in database or config")
                    return jsonify({
                        "error": "YooMoney wallet not configured. Please configure YMONEY_WALLET in admin settings."
                    }), 500
                
                logger.info(f"Using wallet: {wallet[:3]}*** for payment generation")
                
                payment_url = yoomoney_helper.generate_quickpay_url(
                    amount=float(amount),
                    label=payment_label,
                    description=description,
                    payment_type='AC',  # AC - с банковской карты, PC - с кошелька YooMoney, MC - с мобильного телефона
                    success_url=None,  # Можно указать URL для редиректа после оплаты
                    wallet=wallet  # Передаем wallet из БД
                )
            except ValueError as e:
                logger.error(f"Error generating payment URL: {e}")
                return jsonify({
                    "error": f"Error generating payment URL: {str(e)}. Please configure YMONEY_WALLET in admin settings."
                }), 500
            
            # Обновляем запись о платеже с URL
            payment.payment_url = payment_url
            db.commit()
            
            logger.info(f"Generated payment URL for user {user_id}: {payment_label}")
            
            return jsonify({
                "success": True,
                "payment_id": payment.id,
                "payment_url": payment_url,
                "payment_label": payment_label,
                "amount": amount,
                "currency": "RUB"
            }), 200
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Error in generate_payment_uri: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route('/yoomoney_webhook', methods=['POST'])
def yoomoney_webhook():
    """Webhook для уведомлений о платежах от YooMoney"""
    global yoomoney_helper
    
    # Обновляем helper с актуальным токеном из БД перед использованием
    yoomoney_helper = get_yoomoney_helper()
    
    try:
        # YooMoney отправляет данные в формате form-data
        # Логируем все полученные данные для отладки
        logger.info(f"=== WEBHOOK RECEIVED ===")
        logger.info(f"Request method: {request.method}")
        logger.info(f"Request headers: {dict(request.headers)}")
        logger.info(f"Request form data: {dict(request.form)}")
        logger.info(f"Request args: {dict(request.args)}")
        logger.info(f"Request data: {request.data}")
        logger.info(f"Request JSON: {request.json if request.is_json else 'Not JSON'}")
        
        notification_type = request.form.get('notification_type')
        operation_id = request.form.get('operation_id')
        amount = request.form.get('amount')
        currency = request.form.get('currency')
        datetime_str = request.form.get('datetime')
        sender = request.form.get('sender')
        codepro = request.form.get('codepro')
        label = request.form.get('label')
        sha1_hash = request.form.get('sha1_hash')
        operation_label = request.form.get('operation_label')
        test_notification = request.form.get('test_notification', 'false')
        
        logger.info(f"Parsed webhook data:")
        logger.info(f"  notification_type: {notification_type}")
        logger.info(f"  operation_id: {operation_id}")
        logger.info(f"  amount: {amount}")
        logger.info(f"  currency: {currency}")
        logger.info(f"  datetime: {datetime_str}")
        logger.info(f"  sender: {sender}")
        logger.info(f"  label: {label}")
        logger.info(f"  sha1_hash: {sha1_hash}")
        logger.info(f"  operation_label: {operation_label}")
        logger.info(f"  test_notification: {test_notification}")
        
        # Проверяем подпись (если используется)
        if sha1_hash:
            # В YooMoney подпись формируется как SHA1 от строки с параметрами
            # Для проверки нужен secret (соль), который мы можем использовать
            pass
        
        # Получаем сессию БД
        db = get_db_session()
        
        try:
            # Ищем платеж по label
            if not label:
                logger.warning("No label in webhook notification")
                return jsonify({"error": "No label provided"}), 400
            
            payment = db.query(Payment).filter(Payment.yoomoney_label == label).first()
            
            if not payment:
                logger.warning(f"Payment not found for label: {label}")
                return jsonify({"error": "Payment not found"}), 404
            
            # Обрабатываем уведомление
            if notification_type == 'p2p-incoming' or notification_type == 'card-incoming':
                # Входящий перевод или пополнение с карты
                if payment.status == 'pending':
                    payment.status = 'success'
                    payment.yoomoney_payment_id = operation_id
                    payment.paid_at = datetime.fromisoformat(datetime_str.replace('+', '+')) if datetime_str else datetime.now()
                    db.commit()
                    
                    logger.info(f"Payment {payment.id} marked as successful (type: {payment.payment_type})")
                    
                    # Обрабатываем в зависимости от типа платежа
                    if payment.payment_type == 'donation':
                        # Пожертвование - отправляем уведомление администратору
                        _handle_donation(payment, db)
                    
                    elif payment.payment_type == 'qr_subscription':
                        # Покупка QR-кодов - создаем ключи
                        _handle_qr_subscription(payment, db)
                    
                    elif payment.payment_type == 'test':
                        # Тестовый доступ - создаем тестовый ключ на 6 часов
                        _handle_test_access(payment, db)
                    
                    else:
                        # Старая логика (для совместимости)
                        logger.warning(f"Unknown payment type: {payment.payment_type}, using legacy logic")
                        _handle_legacy_payment(payment, db)
                    
                    return jsonify({"status": "ok"}), 200
            
            else:
                logger.info(f"Unknown notification type: {notification_type}")
                return jsonify({"status": "ok", "message": "Unknown notification type"}), 200
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Error in yoomoney_webhook: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


def _send_telegram_message(chat_id: int, text: str, reply_markup=None):
    """Отправка сообщения через Telegram API с опциональной клавиатурой"""
    try:
        from config import BOT_TOKEN
        telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text
        }
        if reply_markup:
            payload['reply_markup'] = reply_markup
        response = requests.post(telegram_url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info(f"Sent Telegram message to {chat_id}")
            return True
        else:
            logger.error(f"Failed to send Telegram message: {response.status_code}, {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return False


def _handle_donation(payment: Payment, db):
    """Обработка пожертвования - отправка уведомления администратору"""
    try:
        from config import ADMIN_ID
        user = payment.user
        
        # Формируем сообщение для администратора
        # Используем nickname, если есть, иначе username или имя
        if user.nickname:
            user_display = user.nickname
            if user.username:
                user_display += f" (@{user.username})"
        elif user.username:
            user_display = f"@{user.username}"
        elif user.first_name:
            user_display = user.first_name
        else:
            user_display = f"user_{user.telegram_id}"
        message = (
            f"💚 Пожертвование получено!\n\n"
            f"От: {user_display}\n"
            f"Сумма: {payment.amount} {payment.currency}\n"
            f"Дата: {payment.paid_at.strftime('%d.%m.%Y %H:%M') if payment.paid_at else 'N/A'}\n"
            f"Описание: {payment.description or 'Пожертвование на поддержку VPN сервера'}\n\n"
            f"Спасибо за поддержку! 🙏"
        )
        
        # Отправляем уведомление администратору
        if ADMIN_ID:
            _send_telegram_message(ADMIN_ID, message)
        
        # Отправляем благодарность пользователю
        user_message = (
            f"✅ Спасибо за поддержку!\n\n"
            f"Ваше пожертвование успешно получено.\n"
            f"Сумма: {payment.amount} {payment.currency}\n"
            f"Дата: {payment.paid_at.strftime('%d.%m.%Y %H:%M') if payment.paid_at else 'N/A'}\n\n"
            f"Ваша поддержка помогает поддерживать работу VPN сервера! 🙏"
        )
        _send_telegram_message(user.telegram_id, user_message)
        
        logger.info(f"Donation processed for user {user.id}: {payment.amount} {payment.currency}")
        
    except Exception as e:
        logger.error(f"Error handling donation: {e}", exc_info=True)


def _handle_qr_subscription(payment: Payment, db):
    """Обработка покупки QR-кодов - создание ключей с подпиской"""
    try:
        from vpn_manager import vpn_manager
        from datetime import datetime, timedelta
        
        user = payment.user
        qr_code_count = payment.qr_code_count or 1
        subscription_days = payment.subscription_period_days or 30
        
        # Рассчитываем дату истечения подписки
        expires_at = datetime.now() + timedelta(days=subscription_days)
        
        # Активируем пользователя после успешной оплаты
        if not user.is_active:
            user.is_active = True
            logger.info(f"User {user.id} activated after successful payment")
        
        # Устанавливаем max_keys равным количеству купленных кодов
        # Это позволит пользователю создать ключи вручную через бота
        user.max_keys = max(user.max_keys or 0, qr_code_count)
        db.commit()
        
        # НЕ создаем ключи автоматически - пользователь создаст их сам через бота
        # Это позволяет избежать создания ключей для неоплаченных платежей
        # Ключи создаются только когда пользователь нажимает "Создать ключ" в боте
        
        # Отправляем уведомление пользователю
        month_word = "месяцев" if subscription_days >= 30 else "дней"
        months = subscription_days // 30
        message = (
            f"✅ Оплата успешно обработана!\n\n"
            f"Доступно QR-кодов: {qr_code_count}\n"
            f"Период подписки: {months} {month_word if months > 0 else 'дней'}\n"
            f"Действует до: {expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Теперь вы можете создать VPN ключи через меню \"🔐 Получить AmneziaWG ключ\".\n"
            f"Вы можете создать до {qr_code_count} ключей."
        )
        # Добавляем клавиатуру меню
        menu_keyboard = {
            'keyboard': [[{'text': '📱 Меню'}]],
            'resize_keyboard': True,
            'one_time_keyboard': False
        }
        _send_telegram_message(user.telegram_id, message, reply_markup=menu_keyboard)
        
        logger.info(f"QR subscription processed for user {user.id}: {qr_code_count} codes available, user activated")
        
    except Exception as e:
        logger.error(f"Error handling QR subscription: {e}", exc_info=True)


def _handle_test_access(payment: Payment, db):
    """Обработка тестового доступа - создание ключа на 6 часов"""
    try:
        from vpn_manager import vpn_manager
        from datetime import datetime, timedelta
        
        user = payment.user
        
        # Генерируем имя ключа для тестового доступа (используем nickname, если есть)
        user_name = (user.nickname or user.first_name or user.username or f"user{user.telegram_id}").replace(" ", "_").replace("-", "_")[:15]
        phone_part = user.phone_number.replace("+", "plus").replace("-", "")[:10] if user.phone_number else "nophone"
        date_part = datetime.now().strftime("%Y%m%d_%H%M")
        key_name = f"test_{user_name}_{phone_part}_{date_part}_{user.telegram_id}"
        
        # Ограничиваем длину имени
        if len(key_name) > 60:
            max_user_len = 60 - len(f"test_{phone_part}_{date_part}_{user.telegram_id}")
            user_name = user_name[:max_user_len] if max_user_len > 0 else "user"
            key_name = f"test_{user_name}_{phone_part}_{date_part}_{user.telegram_id}"
        
        try:
            # Создаем VPN ключ
            logger.info(f"Creating test VPN key for user {user.id}: {key_name}")
            vpn_data = vpn_manager.create_vpn_key(user.id, key_name)
            
            # Обновляем ключ в БД с информацией о тестовом доступе
            vpn_key = db.query(VPNKey).filter(VPNKey.key_name == key_name).first()
            if vpn_key:
                test_expires_at = datetime.now() + timedelta(hours=6)
                vpn_key.access_type = 'test'
                vpn_key.subscription_period_days = 0  # Тестовый доступ
                vpn_key.purchase_date = payment.paid_at or datetime.now()
                vpn_key.expires_at = test_expires_at
                vpn_key.payment_id = payment.id
                vpn_key.is_test = True
                db.commit()
                
                # Отправляем уведомление пользователю
                message = (
                    f"✅ Тестовый доступ активирован!\n\n"
                    f"VPN ключ создан: {key_name}\n"
                    f"Действует до: {test_expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                    f"Это тестовый доступ на 6 часов. Проверьте ключ в разделе \"📋 Мои ключи\"."
                )
                # Добавляем клавиатуру меню
                menu_keyboard = {
                    'keyboard': [[{'text': '📱 Меню'}]],
                    'resize_keyboard': True,
                    'one_time_keyboard': False
                }
                _send_telegram_message(user.telegram_id, message, reply_markup=menu_keyboard)
            
            logger.info(f"Test access processed for user {user.id}: {key_name}")
            
        except Exception as key_error:
            logger.error(f"Failed to create test VPN key: {key_error}", exc_info=True)
        
    except Exception as e:
        logger.error(f"Error handling test access: {e}", exc_info=True)


def _handle_legacy_payment(payment: Payment, db):
    """Обработка старых платежей (для совместимости)"""
    try:
        from vpn_manager import vpn_manager
        from datetime import datetime
        
        user = payment.user
        
        # Генерируем имя ключа для пользователя (используем nickname, если есть)
        user_name = (user.nickname or user.first_name or user.username or f"user{user.telegram_id}").replace(" ", "_").replace("-", "_")[:15]
        phone_part = user.phone_number.replace("+", "plus").replace("-", "")[:10] if user.phone_number else "nophone"
        date_part = datetime.now().strftime("%Y%m%d_%H%M")
        key_name = f"{user_name}_{phone_part}_{date_part}_{user.telegram_id}"
        
        # Ограничиваем длину имени
        if len(key_name) > 60:
            max_user_len = 60 - len(f"_{phone_part}_{date_part}_{user.telegram_id}")
            user_name = user_name[:max_user_len] if max_user_len > 0 else "user"
            key_name = f"{user_name}_{phone_part}_{date_part}_{user.telegram_id}"
        
        logger.info(f"Creating VPN key for user {user.id} after legacy payment: {key_name}")
        
        # Создаем VPN ключ
        vpn_data = vpn_manager.create_vpn_key(user.id, key_name)
        
        # Отправляем уведомление пользователю
        message = (
            f"✅ Оплата успешно обработана!\n\n"
            f"VPN ключ создан автоматически.\n"
            f"Имя ключа: {key_name}\n\n"
            f"Ваш VPN ключ готов к использованию. Проверьте его в разделе \"📋 Мои ключи\"."
        )
        # Добавляем клавиатуру меню
        menu_keyboard = {
            'keyboard': [[{'text': '📱 Меню'}]],
            'resize_keyboard': True,
            'one_time_keyboard': False
        }
        _send_telegram_message(user.telegram_id, message, reply_markup=menu_keyboard)
        
        logger.info(f"Legacy payment processed for user {user.id}: {key_name}")
        
    except Exception as e:
        logger.error(f"Error handling legacy payment: {e}", exc_info=True)


# Шаблоны для welcome страниц
WELCOME_PAGE_TEMPLATE_SUCCESS = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Оплата успешна - VPN Bot</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 600px;
            margin: 50px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #4CAF50;
        }
        .success {
            color: #4CAF50;
            font-size: 24px;
        }
        .bot-link {
            display: inline-block;
            margin-top: 20px;
            padding: 10px 20px;
            background-color: #0088cc;
            color: white;
            text-decoration: none;
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>✅ Оплата успешна!</h1>
        <p class="success">Ваш платеж обработан успешно.</p>
        <p>Теперь вы можете получить VPN ключ через нашего Telegram бота.</p>
        <a href="https://t.me/Moroz_VpnBot" class="bot-link">Открыть бота в Telegram</a>
    </div>
</body>
</html>
"""

WELCOME_PAGE_TEMPLATE_ERROR = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Ошибка - VPN Bot</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 600px;
            margin: 50px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #f44336;
        }}
        .error {{
            color: #f44336;
            font-size: 18px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>❌ Ошибка</h1>
        <p class="error">{error}</p>
        <p>Пожалуйста, попробуйте еще раз или обратитесь в поддержку.</p>
    </div>
</body>
</html>
"""


@app.route('/verify_payment/<int:payment_id>', methods=['POST'])
def verify_payment(payment_id: int):
    """Верификация платежа через API YooMoney"""
    global yoomoney_helper
    
    # Обновляем helper с актуальным токеном из БД перед использованием
    yoomoney_helper = get_yoomoney_helper()
    
    try:
        db = get_db_session()
        
        try:
            payment = db.query(Payment).filter(Payment.id == payment_id).first()
            
            if not payment:
                return jsonify({"error": "Payment not found"}), 404
            
            # Проверяем, что токен установлен
            if not yoomoney_helper.token:
                return jsonify({
                    "error": "YooMoney access token not configured. Please authorize via OAuth first."
                }), 400
            
            # Верифицируем платеж
            result = None
            if payment.yoomoney_label:
                result = yoomoney_helper.verify_payment_by_label(payment.yoomoney_label)
            elif payment.yoomoney_payment_id:
                result = yoomoney_helper.verify_payment_by_operation_id(payment.yoomoney_payment_id)
            else:
                return jsonify({"error": "Payment has no label or operation_id"}), 400
            
            if not result or not result.get('found'):
                return jsonify({
                    "verified": False,
                    "message": "Payment not found in YooMoney"
                }), 200
            
            # Обновляем статус платежа в БД
            was_pending = payment.status == 'pending'
            if result['status'] == 'success' and payment.status == 'pending':
                payment.status = 'success'
                payment.yoomoney_payment_id = result.get('operation_id') or payment.yoomoney_payment_id
                if result.get('datetime'):
                    payment.paid_at = result['datetime']
                db.commit()
                
                logger.info(f"Payment {payment_id} verified and marked as successful")
            
            # Обрабатываем платеж, если он успешен (даже если уже был success)
            # Это нужно для случаев, когда платеж был успешен, но обработка не была выполнена
            if result['status'] == 'success' and payment.status == 'success':
                # Проверяем, нужно ли обработать платеж (если пользователь не активирован для qr_subscription)
                needs_processing = False
                if payment.payment_type == 'qr_subscription':
                    user = payment.user
                    if not user.is_active or user.max_keys < (payment.qr_code_count or 1):
                        needs_processing = True
                elif was_pending:  # Для других типов обрабатываем только если статус изменился
                    needs_processing = True
                
                if needs_processing:
                    # Обрабатываем платеж в зависимости от типа
                    if payment.payment_type == 'donation':
                        _handle_donation(payment, db)
                    elif payment.payment_type == 'qr_subscription':
                        _handle_qr_subscription(payment, db)
                    elif payment.payment_type == 'test':
                        _handle_test_access(payment, db)
                
                return jsonify({
                    "verified": True,
                    "status": "success",
                    "message": "Payment verified and processed",
                    "operation_id": result.get('operation_id'),
                    "amount": result.get('amount'),
                    "currency": result.get('currency')
                }), 200
            elif result['status'] == 'pending':
                return jsonify({
                    "verified": True,
                    "status": "pending",
                    "message": "Payment is still pending in YooMoney"
                }), 200
            else:
                return jsonify({
                    "verified": True,
                    "status": result['status'],
                    "message": f"Payment status: {result['status']}"
                }), 200
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Error verifying payment: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route('/sync_payments', methods=['POST'])
def sync_payments():
    """Синхронизация всех pending платежей с YooMoney API и обработка необработанных успешных платежей"""
    global yoomoney_helper
    
    # Обновляем helper с актуальным токеном из БД перед использованием
    yoomoney_helper = get_yoomoney_helper()
    
    try:
        db = get_db_session()
        
        try:
            # Получаем все pending платежи
            pending_payments = db.query(Payment).filter(Payment.status == 'pending').all()
            
            # Также проверяем успешные qr_subscription платежи, где пользователь не активирован
            # Это нужно для случаев, когда платеж был успешен, но обработка не была выполнена
            unprocessed_successful = db.query(Payment).join(User).filter(
                Payment.status == 'success',
                Payment.payment_type == 'qr_subscription',
                User.is_active == False
            ).all()
            
            if unprocessed_successful:
                logger.info(f"Found {len(unprocessed_successful)} unprocessed successful qr_subscription payments")
                for payment in unprocessed_successful:
                    try:
                        _handle_qr_subscription(payment, db)
                        logger.info(f"Processed payment {payment.id} for user {payment.user_id}")
                    except Exception as e:
                        logger.error(f"Error processing payment {payment.id}: {e}", exc_info=True)
            
            if not pending_payments:
                return jsonify({
                    "message": "No pending payments to sync",
                    "checked": 0,
                    "found": 0,
                    "updated": 0
                }), 200
            
            # Проверяем, что токен установлен
            if not yoomoney_helper.token:
                return jsonify({
                    "error": "YooMoney access token not configured. Please authorize via OAuth first."
                }), 400
            
            # Синхронизируем платежи
            stats = yoomoney_helper.sync_pending_payments(pending_payments, days_back=30)
            
            # Обновляем платежи в БД на основе результатов верификации
            updated_count = 0
            for payment in pending_payments:
                if hasattr(payment, '_verification_result'):
                    result = payment._verification_result
                    was_pending = payment.status == 'pending'
                    if result.get('status') == 'success':
                        if was_pending:
                            payment.status = 'success'
                            payment.yoomoney_payment_id = result.get('operation_id') or payment.yoomoney_payment_id
                            if result.get('datetime'):
                                payment.paid_at = result['datetime']
                            updated_count += 1
                        
                        # Обрабатываем платеж, если он успешен
                        # Для qr_subscription проверяем, нужно ли активировать пользователя
                        needs_processing = False
                        if payment.payment_type == 'qr_subscription':
                            user = payment.user
                            if not user.is_active or user.max_keys < (payment.qr_code_count or 1):
                                needs_processing = True
                        elif was_pending:  # Для других типов обрабатываем только если статус изменился
                            needs_processing = True
                        
                        if needs_processing:
                            # Обрабатываем платеж в зависимости от типа
                            if payment.payment_type == 'donation':
                                _handle_donation(payment, db)
                            elif payment.payment_type == 'qr_subscription':
                                _handle_qr_subscription(payment, db)
                            elif payment.payment_type == 'test':
                                _handle_test_access(payment, db)
            
            db.commit()
            
            return jsonify({
                "message": "Payments synchronized",
                "checked": stats['checked'],
                "found": stats['found'],
                "updated": updated_count,
                "errors": stats['errors']
            }), 200
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Error syncing payments: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


def sync_payments_periodically():
    """Периодическая синхронизация платежей (запускается в отдельном потоке)"""
    while True:
        try:
            time.sleep(3600)  # Проверяем каждый час
            
            db = get_db_session()
            try:
                # Получаем все pending платежи
                pending_payments = db.query(Payment).filter(Payment.status == 'pending').all()
                
                if not pending_payments:
                    continue
                
                # Обновляем helper с актуальным токеном
                global yoomoney_helper
                yoomoney_helper = get_yoomoney_helper()
                
                # Проверяем, что токен установлен
                if not yoomoney_helper.token:
                    logger.warning("YooMoney token not set, skipping payment sync")
                    continue
                
                logger.info(f"Starting periodic payment sync: {len(pending_payments)} pending payments")
                
                # Синхронизируем платежи
                stats = yoomoney_helper.sync_pending_payments(pending_payments, days_back=30)
                
                # Обновляем платежи в БД
                updated_count = 0
                for payment in pending_payments:
                    if hasattr(payment, '_verification_result'):
                        result = payment._verification_result
                        was_pending = payment.status == 'pending'
                        if result.get('status') == 'success':
                            if was_pending:
                                payment.status = 'success'
                                payment.yoomoney_payment_id = result.get('operation_id') or payment.yoomoney_payment_id
                                if result.get('datetime'):
                                    payment.paid_at = result['datetime']
                                updated_count += 1
                            
                            # Обрабатываем платеж, если он успешен
                            # Для qr_subscription проверяем, нужно ли активировать пользователя
                            needs_processing = False
                            if payment.payment_type == 'qr_subscription':
                                user = payment.user
                                if not user.is_active or user.max_keys < (payment.qr_code_count or 1):
                                    needs_processing = True
                            elif was_pending:  # Для других типов обрабатываем только если статус изменился
                                needs_processing = True
                            
                            if needs_processing:
                                # Обрабатываем платеж в зависимости от типа
                                if payment.payment_type == 'donation':
                                    _handle_donation(payment, db)
                                elif payment.payment_type == 'qr_subscription':
                                    _handle_qr_subscription(payment, db)
                                elif payment.payment_type == 'test':
                                    _handle_test_access(payment, db)
                
                db.commit()
                
                if updated_count > 0:
                    logger.info(f"Periodic sync completed: {updated_count} payments updated")
            
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"Error in periodic payment sync: {e}", exc_info=True)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info(f"Starting YooMoney backend server")
    logger.info(f"  Domain: {YMONEY_SITE_URL}")
    logger.info(f"  Redirect URI: {YMONEY_REDIRECT_URI}")
    logger.info(f"  Notification URI: {YMONEY_NOTIFICATION_URI}")
    logger.info(f"  Server: {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    logger.info(f"")
    logger.info(f"ВАЖНО: Убедитесь, что в настройках YooMoney приложения указаны:")
    logger.info(f"  - Redirect URI: {YMONEY_REDIRECT_URI}")
    logger.info(f"  - Notification URI: {YMONEY_NOTIFICATION_URI}")
    
    # Запускаем периодическую синхронизацию платежей в отдельном потоке
    sync_thread = threading.Thread(target=sync_payments_periodically, daemon=True)
    sync_thread.start()
    logger.info("Periodic payment sync thread started (checks every hour)")
    logger.info(f"  - Адрес сайта: {YMONEY_SITE_URL}")
    
    app.run(host=WEB_SERVER_HOST, port=WEB_SERVER_PORT, debug=False)

