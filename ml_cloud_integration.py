#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Интеграция ML Cloud в VPN бот
- Создание платежных ссылок через Tinkoff
- Парсинг истории платежей
- Минимальная сумма: 250 рублей + 2% комиссия
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import requests
from typing import Optional, Dict, List
from datetime import datetime

# Загрузка переменных окружения (как в config.py)
load_dotenv()

from ml_cloud_token_manager import MLCloudTokenManager
from ml_cloud_payment_automation import MLCloudPayment


class MLCloudIntegration:
    """Интеграция ML Cloud для VPN бота"""
    
    BASE_URL = "https://app.ml.cloud"
    MIN_AMOUNT = 25000  # 250 рублей в копейках
    COMMISSION_PERCENT = 2  # 2% комиссия
    
    def __init__(self):
        """Инициализация с автоматическим управлением токенами"""
        email = os.getenv('ML_CLOUD_EMAIL')
        password = os.getenv('ML_CLOUD_PASSWORD')
        
        if not email or not password:
            raise ValueError("Установите ML_CLOUD_EMAIL и ML_CLOUD_PASSWORD в переменные окружения")
        
        self.token_manager = MLCloudTokenManager(email=email, password=password)
        self.payment = None
        self._update_payment_token()
    
    def _update_payment_token(self):
        """Обновить токен для платежей"""
        token = self.token_manager.auto_refresh_if_needed()
        self.payment = MLCloudPayment(jwt_token=token)
    
    def calculate_amount_with_commission(self, amount_rub: int) -> Dict:
        """
        Рассчитать сумму с учетом комиссии
        
        Args:
            amount_rub: Сумма в рублях
        
        Returns:
            dict: {
                'amount_rub': исходная сумма,
                'commission_rub': комиссия,
                'total_rub': сумма с комиссией,
                'total_kopecks': сумма с комиссией в копейках
            }
        """
        if amount_rub < 250:
            raise ValueError(f"Минимальная сумма платежа: 250 рублей. Указано: {amount_rub}")
        
        commission_rub = round(amount_rub * self.COMMISSION_PERCENT / 100, 2)
        total_rub = amount_rub + commission_rub
        total_kopecks = int(total_rub * 100)
        
        return {
            'amount_rub': amount_rub,
            'commission_rub': commission_rub,
            'total_rub': total_rub,
            'total_kopecks': total_kopecks,
            'commission_percent': self.COMMISSION_PERCENT
        }
    
    def create_payment_link(self, amount_rub: int, user_id: Optional[int] = None) -> Dict:
        """
        Создать платежную ссылку через Tinkoff
        
        Args:
            amount_rub: Сумма в рублях (минимум 250)
            user_id: ID пользователя (для логирования)
        
        Returns:
            dict: Информация о платеже с ссылкой
        """
        # Проверяем минимальную сумму
        if amount_rub < 250:
            raise ValueError(f"Минимальная сумма платежа: 250 рублей")
        
        # Рассчитываем сумму с комиссией
        amount_info = self.calculate_amount_with_commission(amount_rub)
        
        # Обновляем токен перед операцией
        self._update_payment_token()
        
        # Создаем платежную ссылку через "Банковская карта" (2% комиссия, прямой Tinkoff)
        try:
            result = self.payment.create_payment_link(
                amount=int(amount_rub * 100),  # Передаем сумму БЕЗ комиссии в копейках
                currency="RUB",
                payment_system="bank-card"  # Используем "Банковская карта" для 2% комиссии
            )
            
            return {
                'payment_url': result['payment_url'],
                'payment_id': result['payment_id'],
                'amount_rub': amount_rub,
                'commission_rub': round(amount_rub * 0.02, 2),  # Примерная комиссия,
                'total_rub': round(amount_rub * 1.02, 2),  # Примерная итоговая сумма,
                'commission_percent': 2,
                'user_id': user_id,
                'created_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            # Если ошибка авторизации - обновляем токен и повторяем
            if "401" in str(e) or "Unauthorized" in str(e):
                print("⚠️  Токен истек, обновляем...")
                self._update_payment_token()
                return self.create_payment_link(amount_rub, user_id)
            raise
    
    def get_payment_history(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        Получить историю платежей
        
        Args:
            limit: Количество записей
            offset: Смещение
        
        Returns:
            list: Список платежей
        """
        # Обновляем токен
        token = self.token_manager.auto_refresh_if_needed()
        
        url = f"{self.BASE_URL}/api/user/finance-history/pager"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        params = {
            'limit': limit,
            'offset': offset
        }
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        # Парсим ответ
        payments = []
        if isinstance(data, dict):
            items = data.get('items', data.get('data', data.get('payments', [])))
        elif isinstance(data, list):
            items = data
        else:
            items = []
        
        for item in items:
            payment = {
                'id': item.get('id') or item.get('payment_id'),
                'amount': item.get('amount'),
                'currency': item.get('currency', 'RUB'),
                'status': item.get('status'),
                'payment_method': item.get('payment_method') or item.get('method'),
                'created_at': item.get('created_at') or item.get('date'),
                'description': item.get('description') or item.get('comment')
            }
            payments.append(payment)
        
        return payments
    
    def check_payment_status(self, payment_id: str) -> Dict:
        """
        Проверить статус платежа
        
        Args:
            payment_id: ID платежа
        
        Returns:
            dict: Статус платежа
        """
        # Обновляем токен
        token = self.token_manager.auto_refresh_if_needed()
        
        # Получаем историю и ищем платеж
        history = self.get_payment_history(limit=100)
        
        for payment in history:
            if payment.get('id') == payment_id:
                return {
                    'payment_id': payment_id,
                    'status': payment.get('status'),
                    'amount': payment.get('amount'),
                    'found': True
                }
        
        return {
            'payment_id': payment_id,
            'status': 'unknown',
            'found': False
        }


def main():
    """Тестирование интеграции"""
    integration = MLCloudIntegration()
    
    print("=" * 80)
    print("ML CLOUD INTEGRATION TEST")
    print("=" * 80)
    
    # Тест создания платежной ссылки
    print("\n1. Тест создания платежной ссылки (250 руб):")
    try:
        result = integration.create_payment_link(amount_rub=250, user_id=123)
        print(f"✅ Ссылка создана:")
        print(f"   Payment ID: {result['payment_id']}")
        print(f"   Сумма: {result['amount_rub']} руб")
        print(f"   Комиссия: {result['commission_rub']} руб ({result['commission_percent']}%)")
        print(f"   Итого: {result['total_rub']} руб")
        print(f"   URL: {result['payment_url'][:100]}...")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    # Тест получения истории
    print("\n2. Тест получения истории платежей:")
    try:
        history = integration.get_payment_history(limit=10)
        print(f"✅ Найдено платежей: {len(history)}")
        for payment in history[:3]:
            print(f"   - {payment.get('id')}: {payment.get('amount')} {payment.get('currency')} ({payment.get('status')})")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

