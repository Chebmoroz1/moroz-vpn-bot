#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Парсер истории платежей ML Cloud
"""

import requests
from datetime import datetime
from typing import List, Dict, Optional
from ml_cloud_token_manager import MLCloudTokenManager


class MLCloudPaymentHistory:
    """Парсер истории платежей ML Cloud"""
    
    BASE_URL = "https://app.ml.cloud"
    
    def __init__(self, email: str = None, password: str = None):
        """Инициализация с автоматическим управлением токенами"""
        import os
        
        email = email or os.getenv('ML_CLOUD_EMAIL')
        password = password or os.getenv('ML_CLOUD_PASSWORD')
        
        if not email or not password:
            raise ValueError("Установите ML_CLOUD_EMAIL и ML_CLOUD_PASSWORD")
        
        self.token_manager = MLCloudTokenManager(email=email, password=password)
    
    def get_history(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        Получить историю платежей
        
        Args:
            limit: Количество записей (по умолчанию 100)
            offset: Смещение (для пагинации)
        
        Returns:
            list: Список платежей с полями:
                - id: ID платежа
                - operation: Тип операции
                - amount: Сумма (положительная для пополнения, отрицательная для списания)
                - currency: Валюта
                - date: Дата и время
                - payment_method: Способ оплаты
                - status: Статус
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
        
        # Парсим ответ (структура может различаться)
        payments = []
        
        # Различные варианты структуры ответа
        items = []
        if isinstance(data, dict):
            items = (
                data.get('items', []) or
                data.get('data', []) or
                data.get('payments', []) or
                data.get('history', []) or
                []
            )
        elif isinstance(data, list):
            items = data
        
        for item in items:
            # Извлекаем сумму (может быть строка вида "1000 ₽" или число)
            amount_str = item.get('amount') or item.get('sum') or item.get('value') or '0'
            if isinstance(amount_str, str):
                # Убираем валюту и пробелы, оставляем только число
                import re
                amount_match = re.search(r'-?\d+\.?\d*', amount_str.replace(',', '.'))
                amount = float(amount_match.group()) if amount_match else 0.0
            else:
                amount = float(amount_str)
            
            # Определяем дату
            date_str = (
                item.get('date') or
                item.get('created_at') or
                item.get('timestamp') or
                item.get('time') or
                ''
            )
            
            payment = {
                'id': str(item.get('id') or item.get('payment_id') or item.get('transaction_id') or ''),
                'operation': item.get('operation') or item.get('type') or item.get('description') or 'Неизвестно',
                'amount': amount,
                'currency': item.get('currency') or item.get('currency_code') or 'RUB',
                'date': date_str,
                'payment_method': item.get('payment_method') or item.get('method') or item.get('payment_system') or '',
                'status': item.get('status') or item.get('state') or 'unknown',
                'raw': item  # Сохраняем исходные данные для отладки
            }
            
            payments.append(payment)
        
        return payments
    
    def get_payment_by_id(self, payment_id: str) -> Optional[Dict]:
        """
        Найти платеж по ID
        
        Args:
            payment_id: ID платежа
        
        Returns:
            dict: Данные платежа или None
        """
        # Ищем в последних 1000 записях
        history = self.get_history(limit=1000, offset=0)
        
        for payment in history:
            if payment['id'] == str(payment_id):
                return payment
        
        return None
    
    def get_recent_payments(self, hours: int = 24, limit: int = 100) -> List[Dict]:
        """
        Получить недавние платежи за последние N часов
        
        Args:
            hours: Количество часов для поиска
            limit: Максимальное количество записей
        
        Returns:
            list: Список платежей
        """
        from datetime import timedelta
        
        history = self.get_history(limit=limit)
        recent_payments = []
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        for payment in history:
            # Пытаемся распарсить дату
            date_str = payment.get('date', '')
            if date_str:
                try:
                    # Различные форматы даты
                    if 'T' in date_str:
                        payment_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    else:
                        # Формат: "22.11.2025 23:46"
                        payment_date = datetime.strptime(date_str, '%d.%m.%Y %H:%M')
                    
                    if payment_date >= cutoff_time:
                        recent_payments.append(payment)
                except:
                    # Если не удалось распарсить дату, включаем в результаты
                    recent_payments.append(payment)
        
        return recent_payments
    
    def get_deposits_only(self, limit: int = 100) -> List[Dict]:
        """
        Получить только пополнения баланса
        
        Args:
            limit: Максимальное количество записей
        
        Returns:
            list: Список пополнений (только положительные суммы)
        """
        history = self.get_history(limit=limit)
        
        deposits = []
        for payment in history:
            # Пополнение = положительная сумма
            if payment['amount'] > 0:
                deposits.append(payment)
        
        return deposits


def main():
    """Тестирование парсера"""
    import os
    
    email = os.getenv('ML_CLOUD_EMAIL')
    password = os.getenv('ML_CLOUD_PASSWORD')
    
    if not email or not password:
        print("Установите переменные окружения:")
        print("  export ML_CLOUD_EMAIL=your@email.com")
        print("  export ML_CLOUD_PASSWORD=your_password")
        return
    
    parser = MLCloudPaymentHistory(email=email, password=password)
    
    print("=" * 80)
    print("ПАРСИНГ ИСТОРИИ ПЛАТЕЖЕЙ ML CLOUD")
    print("=" * 80)
    
    # Получаем последние 10 платежей
    print("\n1. Последние 10 платежей:")
    history = parser.get_history(limit=10)
    
    for payment in history:
        print(f"\n   ID: {payment['id']}")
        print(f"   Операция: {payment['operation']}")
        print(f"   Сумма: {payment['amount']} {payment['currency']}")
        print(f"   Дата: {payment['date']}")
        print(f"   Способ: {payment['payment_method']}")
    
    # Только пополнения
    print("\n2. Только пополнения баланса:")
    deposits = parser.get_deposits_only(limit=10)
    for payment in deposits:
        print(f"   {payment['id']}: +{payment['amount']} {payment['currency']} ({payment['date']})")


if __name__ == '__main__':
    main()

