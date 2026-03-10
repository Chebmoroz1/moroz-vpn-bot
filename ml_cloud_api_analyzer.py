#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализатор API ML Cloud для поиска endpoints оплаты
"""

import json


def analyze_api_structure():
    """Анализ структуры API на основе найденной информации"""
    
    print("=" * 80)
    print("АНАЛИЗ СТРУКТУРЫ ML CLOUD API")
    print("=" * 80)
    
    # Из анализа браузера мы знаем:
    # - Это Next.js приложение
    # - URL структура: /ru-RU/... или /en-US/...
    # - Есть POST запросы к /ru-RU/auth/login
    # - В коде есть упоминания payment, pay, balance
    
    print("\n📋 Наблюдения:")
    print("   - Next.js SPA приложение")
    print("   - Структура URL: /ru-RU/<route> или /en-US/<route>")
    print("   - API запросы, вероятно, через Next.js API routes или внешний API")
    print("   - В коде найдены ключевые слова: payment, pay, balance")
    
    # Типичные endpoints для хостинговых платформ
    potential_endpoints = {
        'billing': [
            '/ru-RU/billing',
            '/ru-RU/balance',
            '/ru-RU/payment',
            '/ru-RU/payments',
            '/api/billing',
            '/api/balance',
            '/api/payment',
            '/api/payments',
        ],
        'auth': [
            '/ru-RU/auth/login',
            '/ru-RU/auth/sign-up',
            '/api/auth/login',
            '/api/auth/token',
        ],
        'account': [
            '/ru-RU/account',
            '/ru-RU/profile',
            '/api/user',
            '/api/account',
        ]
    }
    
    print("\n🔍 Типичные endpoints для поиска:")
    for category, endpoints in potential_endpoints.items():
        print(f"\n   {category.upper()}:")
        for endpoint in endpoints:
            print(f"      - {endpoint}")
    
    print("\n💡 Рекомендации:")
    print("   1. Авторизоваться в системе")
    print("   2. Открыть DevTools → Network")
    print("   3. Перейти в раздел 'Баланс' или 'Оплата'")
    print("   4. Найти API запросы к /api/...")
    print("   5. Проверить запросы создания платежной ссылки")
    
    # Создаем шаблон для тестирования
    test_template = {
        "base_url": "https://app.ml.cloud",
        "endpoints_to_test": [
            "GET /api/billing/balance",
            "GET /api/billing/payments",
            "POST /api/billing/create-payment",
            "POST /api/payment/create",
            "GET /ru-RU/billing",
            "GET /ru-RU/payment",
        ],
        "auth_method": "Bearer token или Session cookie",
        "steps": [
            "1. Авторизоваться через /ru-RU/auth/login",
            "2. Сохранить session cookie или Bearer token",
            "3. Использовать для запросов к API",
            "4. Найти endpoint создания платежной ссылки"
        ]
    }
    
    print("\n📝 Шаблон для тестирования:")
    print(json.dumps(test_template, indent=2, ensure_ascii=False))
    
    return test_template


if __name__ == '__main__':
    analyze_api_structure()

