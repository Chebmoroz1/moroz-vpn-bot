#!/usr/bin/env python3
"""Тестовый скрипт для проверки платежей через API YooMoney"""
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
root_path = Path(__file__).parent
sys.path.insert(0, str(root_path))

from database import SessionLocal, Payment
from yoomoney_helper import YooMoneyHelper
from config_manager import config_manager
from config import YMONEY_CLIENT_ID, YMONEY_CLIENT_SECRET, YMONEY_REDIRECT_URI, YMONEY_WALLET
from datetime import datetime, timedelta

def main():
    print("=" * 80)
    print("ТЕСТОВАЯ ПРОВЕРКА ПЛАТЕЖЕЙ ЧЕРЕЗ API YOOMONEY")
    print("=" * 80)
    print()
    
    # Получаем токен из БД
    token = config_manager.get("YMONEY_ACCESS_TOKEN") if config_manager else None
    
    if not token:
        print("❌ ОШИБКА: Токен YooMoney не найден в БД!")
        print("   Необходимо выполнить OAuth авторизацию через /yoomoney_auth")
        return
    
    print(f"✅ Токен найден: {token[:20]}...")
    print()
    
    # Создаем helper
    helper = YooMoneyHelper(
        client_id=YMONEY_CLIENT_ID,
        client_secret=YMONEY_CLIENT_SECRET,
        redirect_uri=YMONEY_REDIRECT_URI,
        wallet=YMONEY_WALLET,
        token=token
    )
    
    # Получаем информацию об аккаунте
    print("Получение информации об аккаунте...")
    account_info = helper.get_account_info()
    if account_info:
        print(f"✅ Аккаунт: {account_info.account if hasattr(account_info, 'account') else 'N/A'}")
        print(f"   Баланс: {account_info.balance if hasattr(account_info, 'balance') else 'N/A'} RUB")
    else:
        print("❌ Не удалось получить информацию об аккаунте")
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
        
        print(f"Найдено pending платежей за последние 30 дней: {len(pending_payments)}")
        print()
        
        if not pending_payments:
            print("Нет pending платежей для проверки")
            return
        
        # Проверяем каждый платеж
        print("=" * 80)
        print("ПРОВЕРКА ПЛАТЕЖЕЙ")
        print("=" * 80)
        print()
        
        verified_count = 0
        not_found_count = 0
        error_count = 0
        
        for payment in pending_payments:
            print(f"Платеж ID: {payment.id}")
            print(f"  Label: {payment.yoomoney_label}")
            print(f"  Amount: {payment.amount} {payment.currency}")
            print(f"  Created: {payment.created_at.strftime('%Y-%m-%d %H:%M:%S') if payment.created_at else 'N/A'}")
            print(f"  Type: {payment.payment_type}")
            
            # Проверяем платеж
            try:
                result = helper.verify_payment_by_label(payment.yoomoney_label, days_back=30)
                
                if result and result.get('found'):
                    verified_count += 1
                    status = result.get('status', 'unknown')
                    operation_id = result.get('operation_id', 'N/A')
                    amount = result.get('amount', 0)
                    payment_date = result.get('datetime', 'N/A')
                    
                    print(f"  ✅ НАЙДЕН в YooMoney!")
                    print(f"     Operation ID: {operation_id}")
                    print(f"     Status: {status}")
                    print(f"     Amount: {amount} {result.get('currency', 'RUB')}")
                    print(f"     Date: {payment_date}")
                    
                    if status == 'success':
                        print(f"     ⚠️  Платеж успешен, но в БД статус 'pending' - требуется обновление!")
                else:
                    not_found_count += 1
                    print(f"  ❌ НЕ НАЙДЕН в YooMoney (возможно еще не оплачен)")
                
            except Exception as e:
                error_count += 1
                print(f"  ⚠️  ОШИБКА при проверке: {e}")
            
            print()
        
        # Итоговая статистика
        print("=" * 80)
        print("ИТОГОВАЯ СТАТИСТИКА")
        print("=" * 80)
        print(f"Всего проверено: {len(pending_payments)}")
        print(f"  ✅ Найдено в YooMoney: {verified_count}")
        print(f"  ❌ Не найдено: {not_found_count}")
        print(f"  ⚠️  Ошибки: {error_count}")
        print()
        
        # Показываем примеры всех платежей (не только pending)
        print("=" * 80)
        print("ПРИМЕРЫ ВСЕХ ПЛАТЕЖЕЙ (последние 10)")
        print("=" * 80)
        print()
        
        all_payments = db.query(Payment).filter(
            Payment.yoomoney_label.isnot(None)
        ).order_by(Payment.created_at.desc()).limit(10).all()
        
        print(f"{'ID':<5} {'Status':<10} {'Amount':<12} {'Type':<15} {'Label':<40} {'Created':<20}")
        print("-" * 120)
        
        for p in all_payments:
            label_short = p.yoomoney_label[:37] + '...' if p.yoomoney_label and len(p.yoomoney_label) > 40 else (p.yoomoney_label or 'N/A')
            created = p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else 'N/A'
            print(f"{p.id:<5} {p.status:<10} {p.amount:<12} {p.payment_type:<15} {label_short:<40} {created:<20}")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()



