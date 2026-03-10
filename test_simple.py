#!/usr/bin/env python3
import sys
sys.path.insert(0, '/opt/vpn-bot')

print("Script started", file=sys.stderr, flush=True)
print("Hello from test script", flush=True)

try:
    from database import SessionLocal, Payment
    db = SessionLocal()
    count = db.query(Payment).filter(Payment.yoomoney_label.isnot(None)).count()
    print(f"Total payments with labels: {count}", flush=True)
    db.close()
except Exception as e:
    print(f"Error: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc(file=sys.stderr)

print("Script finished", flush=True)



