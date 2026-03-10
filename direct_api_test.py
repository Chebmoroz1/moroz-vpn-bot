#!/usr/bin/env python3
import sys
sys.path.insert(0, '/opt/vpn-bot')
import requests
from config_manager import config_manager

token = config_manager.get("YMONEY_ACCESS_TOKEN") if config_manager else None
print("Token:", "exists" if token else "not found", flush=True)

if token:
    # Прямой запрос к API YooMoney
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    # Получаем информацию об аккаунте
    print("\n=== Account Info ===", flush=True)
    response = requests.post('https://yoomoney.ru/api/account-info', headers=headers)
    print(f"Status: {response.status_code}", flush=True)
    if response.status_code == 200:
        data = response.json()
        print(f"Account: {data.get('account', 'N/A')}", flush=True)
        print(f"Balance: {data.get('balance', 'N/A')}", flush=True)
    else:
        print(f"Error: {response.text}", flush=True)
    
    # Получаем историю операций
    print("\n=== Operation History ===", flush=True)
    params = {
        'type': 'deposition',
        'records': '10'
    }
    response = requests.post('https://yoomoney.ru/api/operation-history', headers=headers, data=params)
    print(f"Status: {response.status_code}", flush=True)
    if response.status_code == 200:
        data = response.json()
        operations = data.get('operations', [])
        print(f"Found {len(operations)} operations:", flush=True)
        for op in operations[:10]:
            print(f"  ID: {op.get('operation_id')}, Label: {op.get('label')}, Amount: {op.get('amount')}, Status: {op.get('status')}", flush=True)
    else:
        print(f"Error: {response.text}", flush=True)



