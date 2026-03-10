#!/usr/bin/env python3
import sys, os
sys.path.insert(0, '/opt/vpn-bot')

from database import SessionLocal, Payment
from yoomoney_helper import YooMoneyHelper
from config_manager import config_manager
from config import YMONEY_CLIENT_ID, YMONEY_CLIENT_SECRET, YMONEY_REDIRECT_URI, YMONEY_WALLET
from datetime import datetime, timedelta

output = []

def log(msg):
    output.append(msg)
    print(msg, flush=True)

log("=" * 80)
log("ПРОВЕРКА ПЛАТЕЖЕЙ")
log("=" * 80)

token = config_manager.get("YMONEY_ACCESS_TOKEN") if config_manager else None
if not token:
    log("ERROR: Token not found")
    sys.exit(1)

log(f"Token: {token[:20]}...")

helper = YooMoneyHelper(
    client_id=YMONEY_CLIENT_ID,
    client_secret=YMONEY_CLIENT_SECRET,
    redirect_uri=YMONEY_REDIRECT_URI,
    wallet=YMONEY_WALLET,
    token=token
)

db = SessionLocal()
try:
    total = db.query(Payment).filter(Payment.yoomoney_label.isnot(None)).count()
    pending = db.query(Payment).filter(Payment.status == 'pending', Payment.yoomoney_label.isnot(None)).count()
    success = db.query(Payment).filter(Payment.status == 'success', Payment.yoomoney_label.isnot(None)).count()
    
    log(f"Total: {total}")
    log(f"Pending: {pending}")
    log(f"Success: {success}")
    
    recent_date = datetime.now() - timedelta(days=30)
    pending_payments = db.query(Payment).filter(
        Payment.status == 'pending',
        Payment.yoomoney_label.isnot(None),
        Payment.created_at >= recent_date
    ).order_by(Payment.created_at.desc()).limit(10).all()
    
    log(f"\nChecking {len(pending_payments)} pending payments:")
    
    for p in pending_payments:
        log(f"\nPayment ID: {p.id}")
        log(f"  Label: {p.yoomoney_label}")
        log(f"  Amount: {p.amount} {p.currency}")
        try:
            result = helper.verify_payment_by_label(p.yoomoney_label, days_back=30)
            if result and result.get('found'):
                log(f"  FOUND: status={result.get('status')}, amount={result.get('amount')}, op_id={result.get('operation_id')}")
            else:
                log(f"  NOT FOUND")
        except Exception as e:
            log(f"  ERROR: {e}")
    
    log("\nLast 10 payments:")
    all_payments = db.query(Payment).filter(Payment.yoomoney_label.isnot(None)).order_by(Payment.created_at.desc()).limit(10).all()
    for p in all_payments:
        label_short = p.yoomoney_label[:40] if p.yoomoney_label else 'N/A'
        log(f"ID: {p.id}, Status: {p.status}, Amount: {p.amount}, Label: {label_short}")
        
finally:
    db.close()

# Сохраняем в файл
with open('/tmp/payment_check_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))

