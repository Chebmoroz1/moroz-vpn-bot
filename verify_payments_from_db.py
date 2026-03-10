#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для верификации платежей из БД через API YooMoney
Согласно документации: https://yoomoney.ru/docs/wallet/using-api/format/protocol-request
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from database import SessionLocal, Payment
from config_manager import config_manager
from datetime import datetime, timedelta

def verify_payments_from_db():
    """Верификация платежей из БД через API YooMoney"""
    
    # Получаем токен
    token = config_manager.get("YMONEY_ACCESS_TOKEN") if config_manager else None
    if not token:
        print("❌ ОШИБКА: Токен YooMoney не найден в БД!")
        print("   Выполните OAuth авторизацию через: http://moroz.myftp.biz:8888/yoomoney_auth")
        return
    
    print("✅ Токен найден")
    print()
    
    # Заголовки для API запросов согласно документации
    # https://yoomoney.ru/docs/wallet/using-api/format/protocol-request
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    # Получаем информацию об аккаунте
    print("=== Информация об аккаунте ===")
    try:
        response = requests.post(
            'https://yoomoney.ru/api/account-info',
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            print(f"Аккаунт: {data.get('account', 'N/A')}")
            print(f"Баланс: {data.get('balance', 'N/A')} RUB")
        else:
            print(f"Ошибка: {response.status_code} - {response.text}")
            return
    except Exception as e:
        print(f"Ошибка при получении информации об аккаунте: {e}")
        return
    
    print()
    
    # Получаем платежи из БД
    db = SessionLocal()
    try:
        # Получаем pending платежи за последние 30 дней
        recent_date = datetime.now() - timedelta(days=30)
        pending_payments = db.query(Payment).filter(
            Payment.status == 'pending',
            Payment.yoomoney_label.isnot(None),
            Payment.created_at >= recent_date
        ).order_by(Payment.created_at.desc()).all()
        
        print(f"=== Найдено {len(pending_payments)} pending платежей для проверки ===")
        print()
        
        if not pending_payments:
            print("Нет pending платежей для проверки")
            return
        
        verified_count = 0
        not_found_count = 0
        error_count = 0
        
        # Проверяем каждый платеж
        for payment in pending_payments:
            print(f"Платеж ID: {payment.id}")
            print(f"  Label: {payment.yoomoney_label}")
            print(f"  Amount: {payment.amount} {payment.currency}")
            print(f"  Created: {payment.created_at.strftime('%Y-%m-%d %H:%M:%S') if payment.created_at else 'N/A'}")
            print(f"  Type: {payment.payment_type}")
            
            try:
                # Запрос к API operation-history с фильтром по label
                # Согласно документации: https://yoomoney.ru/docs/wallet/using-api/format/protocol-request
                params = {
                    'type': 'deposition',  # Только входящие платежи
                    'label': payment.yoomoney_label,
                    'records': '100'  # Максимум 100 записей
                }
                
                response = requests.post(
                    'https://yoomoney.ru/api/operation-history',
                    headers=headers,
                    data=params,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    operations = data.get('operations', [])
                    
                    # Ищем операцию с нужным label
                    found_operation = None
                    for op in operations:
                        if op.get('label') == payment.yoomoney_label:
                            # Проверяем, что это входящий платеж
                            if op.get('direction') == 'in':
                                found_operation = op
                                break
                    
                    if found_operation:
                        verified_count += 1
                        operation_id = found_operation.get('operation_id')
                        status = found_operation.get('status')
                        amount = found_operation.get('amount')
                        op_datetime = found_operation.get('datetime')
                        
                        print(f"  ✅ НАЙДЕН в YooMoney!")
                        print(f"     Operation ID: {operation_id}")
                        print(f"     Status: {status}")
                        print(f"     Amount: {amount}")
                        print(f"     Date: {op_datetime}")
                        
                        # Если платеж успешен, обновляем статус в БД
                        if status == 'success' and payment.status == 'pending':
                            print(f"     ⚠️  Платеж успешен, но в БД статус 'pending' - требуется обновление!")
                            payment.status = 'success'
                            payment.yoomoney_payment_id = operation_id
                            if op_datetime:
                                try:
                                    # Парсим datetime из формата RFC3339
                                    # Формат: YYYY-MM-DDThh:mm:ss.fZZZZZ
                                    dt_str = op_datetime.replace('Z', '+00:00')
                                    payment.paid_at = datetime.fromisoformat(dt_str)
                                except:
                                    payment.paid_at = datetime.now()
                            db.commit()
                            print(f"     ✅ Статус обновлен в БД")
                    else:
                        not_found_count += 1
                        print(f"  ❌ НЕ НАЙДЕН в YooMoney (возможно еще не оплачен)")
                
                elif response.status_code == 401:
                    print(f"  ⚠️  ОШИБКА АВТОРИЗАЦИИ: Токен недействителен или просрочен")
                    error_count += 1
                else:
                    print(f"  ⚠️  ОШИБКА: {response.status_code} - {response.text}")
                    error_count += 1
                    
            except Exception as e:
                error_count += 1
                print(f"  ⚠️  ОШИБКА при проверке: {e}")
            
            print()
        
        # Итоговая статистика
        print("=" * 80)
        print("ИТОГОВАЯ СТАТИСТИКА")
        print("=" * 80)
        print(f"Всего проверено: {len(pending_payments)}")
        print(f"  ✅ Найдено и верифицировано: {verified_count}")
        print(f"  ❌ Не найдено: {not_found_count}")
        print(f"  ⚠️  Ошибки: {error_count}")
        print()
        
        # Показываем примеры всех платежей
        print("=" * 80)
        print("ПОСЛЕДНИЕ 10 ПЛАТЕЖЕЙ ИЗ БД")
        print("=" * 80)
        print()
        
        all_payments = db.query(Payment).filter(
            Payment.yoomoney_label.isnot(None)
        ).order_by(Payment.created_at.desc()).limit(10).all()
        
        print(f"{'ID':<5} {'Status':<10} {'Amount':<12} {'Type':<15} {'Label':<40} {'Created':<20}")
        print("-" * 120)
        
        for p in all_payments:
            label_short = (p.yoomoney_label[:37] + '...') if p.yoomoney_label and len(p.yoomoney_label) > 40 else (p.yoomoney_label or 'N/A')
            created = p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else 'N/A'
            print(f"{p.id:<5} {p.status:<10} {p.amount:<12} {p.payment_type:<15} {label_short:<40} {created:<20}")
        
    finally:
        db.close()

if __name__ == "__main__":
    verify_payments_from_db()



