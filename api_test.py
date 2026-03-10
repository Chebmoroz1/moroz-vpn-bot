#!/usr/bin/env python3
import sys
sys.path.insert(0, '/opt/vpn-bot')

from config_manager import config_manager
from yoomoney_helper import YooMoneyHelper

token = config_manager.get("YMONEY_ACCESS_TOKEN") if config_manager else None
print("Token:", "exists" if token else "not found")

if token:
    helper = YooMoneyHelper(token=token)
    
    # Account info
    account_info = helper.get_account_info()
    if account_info:
        print("Account:", account_info.account if hasattr(account_info, "account") else "N/A")
        print("Balance:", account_info.balance if hasattr(account_info, "balance") else "N/A")
    
    # Operation history
    history = helper.get_operation_history(records=10, operation_type='deposition')
    if history and hasattr(history, "operations") and history.operations:
        print(f"\nFound {len(history.operations)} operations:")
        for op in history.operations:
            op_id = op.operation_id if hasattr(op, "operation_id") else "N/A"
            label = op.label if hasattr(op, "label") else "N/A"
            amount = op.amount if hasattr(op, "amount") else "N/A"
            direction = op.direction if hasattr(op, "direction") else "N/A"
            status = op.status if hasattr(op, "status") else "N/A"
            dt = op.datetime if hasattr(op, "datetime") else "N/A"
            print(f"  ID: {op_id}, Direction: {direction}, Amount: {amount}, Label: {label}, Status: {status}, Date: {dt}")
    else:
        print("\nNo operations found")



