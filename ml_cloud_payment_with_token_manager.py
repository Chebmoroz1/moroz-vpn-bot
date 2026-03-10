#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML Cloud Payment с автоматическим управлением токенами
Интеграция менеджера токенов с классом платежей
"""

import os
import sys
from ml_cloud_token_manager import MLCloudTokenManager
from ml_cloud_payment_automation import MLCloudPayment


class MLCloudPaymentAuto:
    """Класс для работы с платежами с автоматическим управлением токенами"""
    
    def __init__(self, email: str = None, password: str = None, jwt_token: str = None):
        """
        Инициализация
        
        Args:
            email: Email для авторизации (если не указан jwt_token)
            password: Пароль для авторизации (если не указан jwt_token)
            jwt_token: JWT токен напрямую (опционально, для обратной совместимости)
        """
        self.token_manager = None
        self.payment = None
        
        if jwt_token:
            # Используем токен напрямую (старый способ)
            self.payment = MLCloudPayment(jwt_token=jwt_token)
            print("⚠️  Используется прямой токен (без автообновления)")
        else:
            # Используем менеджер токенов
            email = email or os.getenv('ML_CLOUD_EMAIL')
            password = password or os.getenv('ML_CLOUD_PASSWORD')
            
            if not email or not password:
                raise ValueError("Необходимо указать email/password или установить переменные окружения ML_CLOUD_EMAIL и ML_CLOUD_PASSWORD")
            
            self.token_manager = MLCloudTokenManager(email=email, password=password)
            
            # Получаем валидный токен
            token = self.token_manager.auto_refresh_if_needed()
            self.payment = MLCloudPayment(jwt_token=token)
    
    def create_payment_link(self, amount: int, currency: str = "RUB", 
                           payment_system: str = "tinkoff") -> dict:
        """
        Создать платежную ссылку с автоматическим обновлением токена
        
        Args:
            amount: Сумма в копейках (25000 = 250 руб)
            currency: Валюта
            payment_system: Платежная система
        
        Returns:
            dict: Информация о платеже
        """
        # Автоматически обновляем токен перед созданием платежа
        if self.token_manager:
            token = self.token_manager.auto_refresh_if_needed()
            self.payment.jwt_token = token
            self.payment.session.headers['Authorization'] = f'Bearer {token}'
        
        # Создаем платеж
        return self.payment.create_payment_link(
            amount=amount,
            currency=currency,
            payment_system=payment_system
        )


def main():
    """Пример использования"""
    
    print("=" * 80)
    print("ML CLOUD PAYMENT - Автоматическое управление токенами")
    print("=" * 80)
    print()
    
    if len(sys.argv) < 3:
        print("Использование:")
        print("  python3 ml_cloud_payment_with_token_manager.py <email> <password> [amount] [payment_system]")
        print("\nПример:")
        print("  python3 ml_cloud_payment_with_token_manager.py email@example.com password123 25000 tinkoff")
        print("\nИли используйте переменные окружения:")
        print("  export ML_CLOUD_EMAIL=email@example.com")
        print("  export ML_CLOUD_PASSWORD=password123")
        print("  python3 ml_cloud_payment_with_token_manager.py --env 25000 tinkoff")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    amount = int(sys.argv[3]) if len(sys.argv) > 3 else 25000
    payment_system = sys.argv[4] if len(sys.argv) > 4 else "tinkoff"
    
    try:
        # Создаем экземпляр с автоуправлением токенами
        payment = MLCloudPaymentAuto(email=email, password=password)
        
        print(f"✅ Инициализация завершена")
        print(f"   Email: {email}")
        print()
        
        # Создаем платежную ссылку
        result = payment.create_payment_link(
            amount=amount,
            currency="RUB",
            payment_system=payment_system
        )
        
        print("\n" + "=" * 80)
        print("✅ ПЛАТЕЖНАЯ ССЫЛКА СОЗДАНА")
        print("=" * 80)
        print(f"\n💰 Сумма: {result['amount']/100} {result['currency']}")
        print(f"🔑 Payment ID: {result['payment_id']}")
        print(f"💳 Платежная система: {result['payment_system']}")
        print(f"\n🔗 Ссылка на оплату:")
        print(f"   {result['payment_url']}")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

