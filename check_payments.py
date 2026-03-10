#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Скрипт для проверки платежей через API YooMoney"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, Payment
from yoomoney_helper import YooMoneyHelper
from config_manager import config_manager
from config import YMONEY_CLIENT_ID, YMONEY_CLIENT_SECRET, YMONEY_REDIRECT_URI, YMONEY_WALLET
from datetime import datetime, timedelta

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    
    print("=" * 80)
    print("ПРОВЕРКА ПЛАТЕЖЕЙ ЧЕРЕЗ API YOOMONEY")
    print("=" * 80)
    print()
    
    # Получаем токен
    token = config_manager.get("YMONEY_ACCESS_TOKEN") if config_manager else None
    if not token:
        print("❌ ОШИБКА: Токен YooMoney не найден!")
        print("   Выполните OAuth авторизацию через: http://moroz.myftp.biz:8888/yoomoney_auth")
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
        account = account_info.account if hasattr(account_info, 'account') else 'N/A'
        balance = account_info.balance if hasattr(account_info, 'balance') else 'N/A'
        print(f"✅ Аккаунт: {account}")
        print(f"   Баланс: {balance} RUB")
    else:
        print("❌ Не удалось получить информацию об аккаунте")
    print()
    
    # Получаем платежи из БД
    db = SessionLocal()
    try:
        # Статистика
        total = db.query(Payment).filter(Payment.yoomoney_label.isnot(None)).count()
        pending = db.query(Payment).filter(
            Payment.status == 'pending',
            Payment.yoomoney_label.isnot(None)
        ).count()
        success = db.query(Payment).filter(
            Payment.status == 'success',
            Payment.yoomoney_label.isnot(None)
        ).count()
        
        print("СТАТИСТИКА ПЛАТЕЖЕЙ:")
        print(f"  Всего с лейблами: {total}")
        print(f"  Pending: {pending}")
        print(f"  Success: {success}")
        print()
        
        # Получаем pending платежи за последние 30 дней
        recent_date = datetime.now() - timedelta(days=30)
        pending_payments = db.query(Payment).filter(
            Payment.status == 'pending',
            Payment.yoomoney_label.isnot(None),
            Payment.created_at >= recent_date
        ).order_by(Payment.created_at.desc()).all()
        
        print(f"Pending платежей за последние 30 дней: {len(pending_payments)}")
        print()
        
        if not pending_payments:
            print("Нет pending платежей для проверки")
            return
        
        # Проверяем каждый платеж
        print("=" * 80)
        print("ПРОВЕРКА ПЛАТЕЖЕЙ")
        print("=" * 80)
        print()
        
        verified = 0
        not_found = 0
        errors = 0
        
        for payment in pending_payments:
            print(f"Платеж ID: {payment.id}")
            print(f"  Label: {payment.yoomoney_label}")
            print(f"  Amount: {payment.amount} {payment.currency}")
            print(f"  Created: {payment.created_at.strftime('%Y-%m-%d %H:%M:%S') if payment.created_at else 'N/A'}")
            print(f"  Type: {payment.payment_type}")
            
            try:
                result = helper.verify_payment_by_label(payment.yoomoney_label, days_back=30)
                
                if result and result.get('found'):
                    verified += 1
                    status = result.get('status', 'unknown')
                    op_id = result.get('operation_id', 'N/A')
                    amount = result.get('amount', 0)
                    pay_date = result.get('datetime', 'N/A')
                    
                    print(f"  ✅ НАЙДЕН в YooMoney!")
                    print(f"     Operation ID: {op_id}")
                    print(f"     Status: {status}")
                    print(f"     Amount: {amount} {result.get('currency', 'RUB')}")
                    print(f"     Date: {pay_date}")
                    
                    if status == 'success' and payment.status == 'pending':
                        # Обновляем статус в БД
                        payment.status = 'success'
                        payment.yoomoney_payment_id = op_id
                        db.commit()
                        print(f"     ✅ Статус обновлен в БД на 'success'")
                else:
                    not_found += 1
                    print(f"  ❌ НЕ НАЙДЕН (возможно еще не оплачен)")
                
            except Exception as e:
                errors += 1
                print(f"  ⚠️  ОШИБКА: {e}")
            
            print()
        
        # Итоги
        print("=" * 80)
        print("ИТОГИ")
        print("=" * 80)
        print(f"Проверено: {len(pending_payments)}")
        print(f"  ✅ Найдено: {verified}")
        print(f"  ❌ Не найдено: {not_found}")
        print(f"  ⚠️  Ошибки: {errors}")
        print()
        
        # Показываем примеры всех платежей
        print("=" * 80)
        print("ПОСЛЕДНИЕ 10 ПЛАТЕЖЕЙ")
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
    main()


