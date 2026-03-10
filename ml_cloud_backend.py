"""Веб-бэкенд для интеграции с ML Cloud (замена YooMoney)"""
import os
import logging
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from config import (
    WEB_SERVER_HOST, WEB_SERVER_PORT, ADMIN_ID
)
from database import get_db_session, Payment, User, VPNKey
from ml_cloud_helper import get_ml_cloud_helper
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Инициализация helper для работы с ML Cloud
def get_ml_cloud_helper_instance():
    """Получить инициализированный helper для ML Cloud"""
    try:
        return get_ml_cloud_helper()
    except Exception as e:
        logger.error(f"Error initializing ML Cloud helper: {e}")
        raise

ml_cloud_helper = get_ml_cloud_helper_instance()


@app.route('/health', methods=['GET'])
def health():
    """Проверка здоровья сервиса"""
    return jsonify({"status": "ok", "service": "ml_cloud_backend"}), 200


@app.route('/generate_payment_uri', methods=['POST'])
def generate_payment_uri():
    """Генерация URI для оплаты через ML Cloud (Tinkoff)"""
    global ml_cloud_helper
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        user_id = data.get('user_id')
        amount = data.get('amount')
        description = data.get('description', 'VPN доступ')
        
        if not user_id or not amount:
            return jsonify({"error": "user_id and amount are required"}), 400
        
        # Проверяем минимальную сумму
        amount_float = float(amount)
        if amount_float < 250.0:
            return jsonify({
                "error": f"Минимальная сумма платежа: {250.0} рублей. "
                        f"Указано: {amount_float} рублей. "
                        f"Комиссия {2}% включена."
            }), 400
        
        # Получаем сессию БД
        db = get_db_session()
        
        try:
            # Проверяем существование пользователя
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            # Получаем дополнительные параметры для подписок
            payment_type = data.get('payment_type', 'donation')  # 'donation' | 'qr_subscription' | 'test'
            qr_code_count = data.get('qr_code_count', None)
            subscription_period_days = data.get('subscription_period_days', None)
            is_test = data.get('is_test', False)
            
            # Генерируем уникальный label для платежа
            if payment_type == 'donation':
                payment_label = f"donation_{user_id}_{int(datetime.now().timestamp())}"
            elif payment_type == 'qr_subscription':
                payment_label = f"qr_{user_id}_{int(datetime.now().timestamp())}"
            else:
                payment_label = f"vpn_{user_id}_{int(datetime.now().timestamp())}"
            
            # Рассчитываем сумму с комиссией
            from ml_cloud_integration import MLCloudIntegration
            ml_integration = MLCloudIntegration()
            amount_info = ml_integration.calculate_amount_with_commission(int(amount_float))
            
            # Создаем запись о платеже в БД
            payment = Payment(
                user_id=user_id,
                amount=str(amount_info['total_rub']),  # Сохраняем итоговую сумму с комиссией
                currency='RUB',
                status='pending',
                payment_method='ml_cloud_tinkoff',
                payment_type=payment_type,
                yoomoney_label=payment_label,  # Используем существующее поле для совместимости
                description=description,
                expires_at=datetime.now() + timedelta(hours=24),  # Ссылка действует 24 часа
                qr_code_count=qr_code_count,
                subscription_period_days=subscription_period_days,
                is_test=is_test
            )
            db.add(payment)
            db.commit()
            db.refresh(payment)
            
            # Генерируем платежную ссылку через ML Cloud
            try:
                payment_url = ml_cloud_helper.generate_quickpay_url(
                    amount=amount_float,
                    label=payment_label,
                    description=description,
                    payment_type='AC',  # Оставлено для совместимости, не используется в ML Cloud
                    success_url=None,
                    user_id=user.telegram_id if hasattr(user, 'telegram_id') else user.id
                )
                
                # Сохраняем payment_id ML Cloud если есть
                # (можно получить из payment_flow, но пока оставляем пустым)
                
            except ValueError as e:
                logger.error(f"Error generating payment URL: {e}")
                return jsonify({
                    "error": str(e)
                }), 400
            except Exception as e:
                logger.error(f"Error generating payment URL: {e}", exc_info=True)
                return jsonify({
                    "error": f"Error generating payment URL: {str(e)}"
                }), 500
            
            # Обновляем запись о платеже с URL
            payment.payment_url = payment_url
            db.commit()
            
            logger.info(f"Generated ML Cloud payment URL for user {user_id}: {payment_label}")
            
            return jsonify({
                "commission": amount_info['commission_rub'],
                "commission_percent": amount_info['commission_percent'],
                "currency": "RUB"
            }), 200
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Error in generate_payment_uri: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route('/check_payment_status', methods=['POST'])
def check_payment_status():
    """Проверка статуса платежа через ML Cloud"""
    global ml_cloud_helper
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        payment_id = data.get('payment_id')
        payment_label = data.get('payment_label')
        
        if not payment_id and not payment_label:
            return jsonify({"error": "payment_id or payment_label is required"}), 400
        
        # Получаем сессию БД
        db = get_db_session()
        
        try:
            # Ищем платеж в БД
            if payment_id:
                payment = db.query(Payment).filter(Payment.id == payment_id).first()
            else:
                payment = db.query(Payment).filter(Payment.yoomoney_label == payment_label).first()
            
            if not payment:
                return jsonify({"error": "Payment not found"}), 404
            
            # Проверяем статус через ML Cloud
            # Проверяем старые неудачные платежи этого пользователя перед проверкой текущего
            failed_payments = db.query(Payment).filter(
                Payment.user_id == payment.user_id,
                Payment.status == "failed",
                Payment.payment_method == "ml_cloud_tinkoff"
            ).all()
            
            if failed_payments:
                from ml_cloud_payment_tracker import MLCloudPaymentTracker
                tracker_old = MLCloudPaymentTracker()
                for failed_payment in failed_payments:
                    ml_cloud_payment_id_old = failed_payment.yoomoney_label
                    if ml_cloud_payment_id_old:
                        try:
                            status_old = tracker_old.check_payment_status(str(ml_cloud_payment_id_old))
                            if status_old.get("found"):
                                failed_logger.info(f"✅ Payment {payment.id} confirmed"); payment.status = "confirmed"
                                logger.info(f"✅ Old failed payment {failed_payment.id} is now confirmed")
                                db.commit()
                        except Exception as e:
                            logger.warning(f"⚠️  Error checking old failed payment {failed_payment.id}: {e}")
            try:
                from ml_cloud_payment_tracker import MLCloudPaymentTracker
                from ml_cloud_payment_history import MLCloudPaymentHistory
                
                ml_cloud_payment_id = None
                if payment.payment_url:
                    # Извлекаем payment_id из URL или используем yoomoney_label
                    ml_cloud_payment_id = payment.yoomoney_label
                
                if not ml_cloud_payment_id:
                    # Если нет ML Cloud payment_id, ищем по сумме
                    tracker = MLCloudPaymentTracker()
                    amount_float = float(payment.amount)
                    found_payment = tracker.find_payment_by_amount(
                        amount=amount_float,
                        currency=payment.currency,
                        recent_hours=48
                    )
                    if found_payment:
                        ml_cloud_payment_id = found_payment.get("id")
                
                if ml_cloud_payment_id:
                    tracker = MLCloudPaymentTracker()
                    status = tracker.check_payment_status(str(ml_cloud_payment_id))
                    
                    if status.get("found") and status.get("confirmed", False):
                        # Платеж найден - обновляем статус в БД
                        logger.info(f"✅ Payment {payment.id} confirmed"); payment.status = "confirmed"
                        db.commit()
                        return jsonify({
                            "payment_id": payment.id,
                            "status": "confirmed",
                            "amount": payment.amount,
                            "currency": payment.currency,
                            "ml_cloud_status": status
                        }), 200
                    else:
                        # Платеж не найден - помечаем как неудачу (если это не первая проверка)
                        if payment.status == "pending":
                            # Первая проверка - оставляем pending
                            pass
                        elif payment.status == "failed":
                            # Уже была неудача - оставляем failed
                            pass
                        else:
                            # Вторая и последующие проверки без результата - помечаем как failed
                            logger.info(f"❌ Payment {payment.id} not found, marking as failed"); payment.status = "failed"
                            db.commit()
                        
                        return jsonify({
                            "payment_id": payment.id,
                            "status": payment.status,
                            "amount": payment.amount,
                            "currency": payment.currency,
                            "found": False
                        }), 200
                else:
                    # Не удалось найти payment_id для проверки
                    return jsonify({
                        "payment_id": payment.id,
                        "status": payment.status,
                        "amount": payment.amount,
                        "currency": payment.currency,
                        "error": "Could not find ML Cloud payment ID"
                    }), 200
                    
            except Exception as e:
                logger.error(f"Error checking payment status via ML Cloud: {e}", exc_info=True)
                # Возвращаем статус из БД в случае ошибки
                return jsonify({
                    "payment_id": payment.id,
                    "status": payment.status,
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "error": str(e)
                }), 200
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Error in check_payment_status: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    # Для разработки
    app.run(host=WEB_SERVER_HOST, port=WEB_SERVER_PORT, debug=True)

