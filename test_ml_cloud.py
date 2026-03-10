#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тест ML Cloud интеграции"""

import sys
import os
sys.path.insert(0, "/opt/vpn-bot")

from ml_cloud_integration import MLCloudIntegration

print("🧪 Тестирование создания платежной ссылки (250 руб)...")
print("=" * 60)

try:
    integration = MLCloudIntegration()
    result = integration.create_payment_link(amount_rub=250, user_id=123)
    
    print("✅ Успех!")
    print(f"Payment ID: {result.get('payment_id')}")
    payment_url = result.get('payment_url', '')
    if payment_url:
        print(f"URL: {payment_url[:100]}...")
    print(f"Сумма: {result.get('amount_rub')} руб")
    print(f"Комиссия: {result.get('commission_rub')} руб ({result.get('commission_percent')}%)")
    print(f"Итого: {result.get('total_rub')} руб")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()

