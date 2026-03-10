#!/usr/bin/env python3
import sys
sys.path.insert(0, '/opt/vpn-bot')

from database import SessionLocal, Payment
from yoomoney_helper import YooMoneyHelper
from config_manager import config_manager
from config import YMONEY_CLIENT_ID, YMONEY_CLIENT_SECRET, YMONEY_REDIRECT_URI, YMONEY_WALLET
from datetime import datetime, timedelta

print("=" * 80)
print("ПРОВЕРКА ПЛАТЕЖЕЙ")
print("=" * 80)

# Получаем токен
token = config_manager.get("YMONEY_ACCESS_TOKEN") if config_manager else None
if not token:
    print("ERROR: Token not found")
    sys.exit(1)

print(f"Token: {token[:20]}...")

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
    recent_date = datetime.now() - timedelta(days=30)
    pending = db.query(Payment).filter(
        Payment.status == 'pending',
        Payment.yoomoney_label.isnot(None),
        Payment.created_at >= recent_date
    ).all()
    
    print(f"\nPending payments: {len(pending)}")
    
    for p in pending[:5]:  # Проверяем первые 5
        print(f"\nPayment ID: {p.id}, Label: {p.yoomoney_label}")
        result = helper.verify_payment_by_label(p.yoomoney_label, days_back=30)
        if result and result.get('found'):
            print(f"  FOUND: {result.get('status')}, Amount: {result.get('amount')}")
        else:
            print(f"  NOT FOUND")
finally:
    db.close()



