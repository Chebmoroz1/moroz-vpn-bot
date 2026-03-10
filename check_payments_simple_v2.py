#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, Payment
from yoomoney_helper import YooMoneyHelper
from config_manager import config_manager
from config import YMONEY_CLIENT_ID, YMONEY_CLIENT_SECRET, YMONEY_REDIRECT_URI, YMONEY_WALLET
from datetime import datetime, timedelta

# Принудительно отключаем буферизацию
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 0)

print("=" * 80, flush=True)
print("ПРОВЕРКА ПЛАТЕЖЕЙ", flush=True)
print("=" * 80, flush=True)
print(flush=True)

# Получаем токен
token = config_manager.get("YMONEY_ACCESS_TOKEN") if config_manager else None
if not token:
    print("ERROR: Token not found", flush=True)
    sys.exit(1)

print(f"Token: {token[:20]}...", flush=True)
print(flush=True)

# Создаем helper
helper = YooMoneyHelper(
    client_id=YMONEY_CLIENT_ID,
    client_secret=YMONEY_CLIENT_SECRET,
    redirect_uri=YMONEY_REDIRECT_URI,
    wallet=YMONEY_WALLET,
    token=token
)

# Получаем платежи
db = SessionLocal()
try:
    total = db.query(Payment).filter(Payment.yoomoney_label.isnot(None)).count()
    pending = db.query(Payment).filter(Payment.status == 'pending', Payment.yoomoney_label.isnot(None)).count()
    success = db.query(Payment).filter(Payment.status == 'success', Payment.yoomoney_label.isnot(None)).count()
    
    print(f"Total: {total}", flush=True)
    print(f"Pending: {pending}", flush=True)
    print(f"Success: {success}", flush=True)
    print(flush=True)
    
    # Получаем pending платежи
    recent_date = datetime.now() - timedelta(days=30)
    pending_payments = db.query(Payment).filter(
        Payment.status == 'pending',
        Payment.yoomoney_label.isnot(None),
        Payment.created_at >= recent_date
    ).order_by(Payment.created_at.desc()).limit(10).all()
    
    print(f"Checking {len(pending_payments)} pending payments...", flush=True)
    print(flush=True)
    
    for p in pending_payments:
        print(f"Payment ID: {p.id}, Label: {p.yoomoney_label}", flush=True)
        try:
            result = helper.verify_payment_by_label(p.yoomoney_label, days_back=30)
            if result and result.get('found'):
                print(f"  FOUND: status={result.get('status')}, amount={result.get('amount')}", flush=True)
            else:
                print(f"  NOT FOUND", flush=True)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
        print(flush=True)
    
    # Показываем последние платежи
    print("Last 10 payments:", flush=True)
    all_payments = db.query(Payment).filter(Payment.yoomoney_label.isnot(None)).order_by(Payment.created_at.desc()).limit(10).all()
    for p in all_payments:
        label_short = p.yoomoney_label[:40] if p.yoomoney_label else 'N/A'
        print(f"ID: {p.id}, Status: {p.status}, Amount: {p.amount}, Label: {label_short}", flush=True)
        
finally:
    db.close()



