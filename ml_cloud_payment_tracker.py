#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Отслеживание платежей ML Cloud
- Парсинг истории платежей
- Поиск платежа по ID или сумме
- Проверка статуса платежа
"""

import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from ml_cloud_payment_history import MLCloudPaymentHistory


class MLCloudPaymentTracker:
    """Отслеживание статуса платежей"""
    
    def __init__(self, email: str = None, password: str = None):
        """Инициализация"""
        self.history_parser = MLCloudPaymentHistory(email=email, password=password)
        self.check_delay = 30  # Задержка между проверками (секунды)
        self.max_wait_time = 3600  # Максимальное время ожидания (1 час)
    
    def find_payment_by_id(self, payment_id: str, recent_hours: int = 24) -> Optional[Dict]:
        """
        Найти платеж по ID в истории
        
        Args:
            payment_id: ID платежа
            recent_hours: За сколько часов искать (для оптимизации)
        
        Returns:
            dict: Данные платежа или None
        """
        # Получаем недавние платежи
        history = self.history_parser.get_recent_payments(hours=recent_hours, limit=1000)
        
        for payment in history:
            if payment['id'] == str(payment_id):
                return payment
        
        return None
    
    def find_payment_by_amount(self, amount: float, currency: str = 'RUB', 
                               recent_hours: int = 24, tolerance: float = 0.01) -> Optional[Dict]:
        """
        Найти платеж по сумме (для случаев когда ID неизвестен)
        
        Args:
            amount: Сумма платежа
            currency: Валюта
            recent_hours: За сколько часов искать
            tolerance: Допустимое отклонение суммы (для округления)
        
        Returns:
            dict: Данные платежа или None
        """
        history = self.history_parser.get_recent_payments(hours=recent_hours, limit=1000)
        
        for payment in history:
            if payment['currency'] == currency:
                # Проверяем совпадение суммы (с учетом округления)
                if abs(payment['amount'] - amount) <= tolerance:
                    # Предпочитаем пополнения (положительные суммы)
                    if payment['amount'] > 0:
                        return payment
        
        return None
    
    def wait_for_payment(self, payment_id: str, timeout: int = 3600, 
                        check_interval: int = 30) -> Optional[Dict]:
        """
        Ожидать появления платежа в истории
        
        Args:
            payment_id: ID платежа для поиска
            timeout: Максимальное время ожидания (секунды)
            check_interval: Интервал проверки (секунды)
        
        Returns:
            dict: Данные платежа или None (если не найден)
        """
        start_time = time.time()
        check_count = 0
        
        print(f"🔍 Ожидание платежа {payment_id}...")
        
        while time.time() - start_time < timeout:
            check_count += 1
            
            # Ищем платеж
            payment = self.find_payment_by_id(payment_id, recent_hours=24)
            
            if payment:
                elapsed = time.time() - start_time
                print(f"✅ Платеж найден через {elapsed:.0f} секунд ({check_count} проверок)")
                return payment
            
            # Ждем перед следующей проверкой
            if time.time() - start_time < timeout:
                time.sleep(check_interval)
                print(f"⏳ Проверка #{check_count}... (прошло {time.time() - start_time:.0f}с)")
        
        print(f"❌ Платеж не найден за {timeout} секунд")
        return None
    
    def wait_for_payment_by_amount(self, amount: float, currency: str = 'RUB',
                                   timeout: int = 3600, check_interval: int = 30) -> Optional[Dict]:
        """
        Ожидать появления платежа по сумме
        
        Args:
            amount: Сумма платежа
            currency: Валюта
            timeout: Максимальное время ожидания
            check_interval: Интервал проверки
        
        Returns:
            dict: Данные платежа или None
        """
        start_time = time.time()
        check_count = 0
        
        print(f"🔍 Ожидание платежа на сумму {amount} {currency}...")
        
        while time.time() - start_time < timeout:
            check_count += 1
            
            # Ищем платеж
            payment = self.find_payment_by_amount(amount, currency, recent_hours=24)
            
            if payment:
                elapsed = time.time() - start_time
                print(f"✅ Платеж найден через {elapsed:.0f} секунд ({check_count} проверок)")
                return payment
            
            time.sleep(check_interval)
            print(f"⏳ Проверка #{check_count}... (прошло {time.time() - start_time:.0f}с)")
        
        print(f"❌ Платеж не найден за {timeout} секунд")
        return None
    
    def check_payment_status(self, payment_id: str) -> Dict:
        """
        Проверить статус платежа
        
        Args:
            payment_id: ID платежа
        
        Returns:
            dict: {
                'found': bool - найден ли платеж
                'confirmed': bool - подтвержден ли платеж (found=True означает confirmed)
                'status': str - статус платежа
                'amount': float - сумма
                'payment': dict - полные данные платежа
            }
        """
        payment = self.find_payment_by_id(payment_id, recent_hours=168)  # За неделю
        
        if payment:
            # Если платеж найден в истории - он подтвержден
            return {
                'found': True,
                'confirmed': True,  # Найден в истории = подтвержден
                'status': payment.get('status', 'confirmed'),
                'amount': payment.get('amount', 0),
                'currency': payment.get('currency', 'RUB'),
                'date': payment.get('date'),
                'payment': payment
            }
        
        return {
            'found': False,
            'confirmed': False,
            'status': 'not_found',
            'payment_id': payment_id
        }
    
    def monitor_payment(self, payment_id: str, callback=None, 
                       max_wait: int = 3600, check_interval: int = 30):
        """
        Мониторинг платежа с callback при успехе
        
        Args:
            payment_id: ID платежа
            callback: Функция callback(payment_data) - вызывается при успешном платеже
            max_wait: Максимальное время ожидания
            check_interval: Интервал проверки
        """
        payment = self.wait_for_payment(payment_id, timeout=max_wait, check_interval=check_interval)
        
        if payment and callback:
            callback(payment)
        
        return payment


def main():
    """Тестирование отслеживания"""
    import os
    
    email = os.getenv('ML_CLOUD_EMAIL')
    password = os.getenv('ML_CLOUD_PASSWORD')
    
    if not email or not password:
        print("Установите ML_CLOUD_EMAIL и ML_CLOUD_PASSWORD")
        return
    
    tracker = MLCloudPaymentTracker(email=email, password=password)
    
    print("=" * 80)
    print("ОТСЛЕЖИВАНИЕ ПЛАТЕЖЕЙ ML CLOUD")
    print("=" * 80)
    
    # Пример: проверка существующего платежа
    payment_id = "1228177"  # Пример ID из истории
    
    print(f"\n1. Проверка платежа {payment_id}:")
    status = tracker.check_payment_status(payment_id)
    print(f"   Найден: {status['found']}")
    if status['found']:
        print(f"   Статус: {status['status']}")
        print(f"   Сумма: {status['amount']} {status['currency']}")
        print(f"   Дата: {status['date']}")
    
    # Пример: поиск по сумме
    print(f"\n2. Поиск платежа на сумму 1000 RUB:")
    payment = tracker.find_payment_by_amount(1000.0, 'RUB', recent_hours=168)
    if payment:
        print(f"   Найден: {payment['id']}")
        print(f"   Дата: {payment['date']}")
        print(f"   Способ: {payment['payment_method']}")


if __name__ == '__main__':
    main()

