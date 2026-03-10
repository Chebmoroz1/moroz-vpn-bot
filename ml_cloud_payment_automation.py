#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматическая генерация платежных ссылок для ML Cloud
"""

import requests
import logging
import json
import jwt
from typing import Optional, Dict


class MLCloudPayment:
    """Класс для работы с платежами ML Cloud"""
    BASE_URL = "https://app.ml.cloud"
    def __init__(self, jwt_token: Optional[str] = None):
        """
        Инициализация
        Args:
            jwt_token: JWT токен из localStorage (ключ: ve2wv3wGs8t3g45Fds)
        """
        import logging
        self.logger = logging.getLogger(__name__)
        self.jwt_token = jwt_token
        self.session = requests.Session()
        if jwt_token:
            self.session.headers.update({
                'Authorization': f'Bearer {jwt_token}',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
    def create_payment(self, amount: int, currency: str = "RUB") -> Dict:
        """
        Создать платеж (deposit)
        Args:
            amount: Сумма в рублях (в копейках, например: 25000 = 250 руб)
            currency: Валюта (RUB/USD)
        Returns:
            dict: Ответ от API с payment_id
        """
        url = f"{self.BASE_URL}/api/billing/deposit"
        # ML Cloud API требует amount как строку
        # Конвертируем копейки в рубли для API
        logger = logging.getLogger(__name__)
        amount_rub = amount / 100.0
        logger.info(f"📝 create_payment: {amount} копеек = {amount_rub} рублей")
        payload = {
            "amount": str(amount_rub),
            "currency": currency
        }
        response = self.session.post(url, json=payload)
    def get_payment_params(self, payment_id: str) -> Dict:
        """
        Получить параметры платежа (core)
        
        Args:
            payment_id: ID платежа
        
        Returns:
            dict: Параметры платежа
        """
        url = f"{self.BASE_URL}/api/billing/payment/core/{payment_id}/payment-params"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_core_payment_id(self, deposit_response: Dict) -> str:
        """
        Получить core payment_id из ответа deposit
        Args:
            deposit_response: Ответ от create_payment
        Returns:
            str: Core payment_id
        """
        # В ответе deposit может быть core_payment_id или другой идентификатор
        return (
            deposit_response.get('core_payment_id') or
            deposit_response.get('payment_id') or
            deposit_response.get('id')
        )
    def choose_payment_system(self, payment_id: str, payment_system: str = "bank-card") -> Dict:
        """
        Выбрать платежную систему
        Args:
            payment_id: ID платежа
            payment_system: Название платежной системы 
                          - "bank-card" для "Банковская карта" (2% комиссия, прямой Tinkoff)
                          - "tinkoff" для "Тинькоф" (4% комиссия, через YooKassa)
        Returns:
            dict: Ответ от API
        """
        # ВАЖНО: для choose-payment-system используем core_payment_id в URL
        # URL: /api/billing/payment/core/{core_payment_id}/choose-payment-system
        url = f"{self.BASE_URL}/api/billing/payment/core/{payment_id}/choose-payment-system"
        # ML Cloud API использует camelCase: paymentSystem
        # В Payload нужно отправлять и id (core payment_id) и paymentSystem
        payload = {
            "id": payment_id,  # core payment_id (тот же что в URL)
            "paymentSystem": payment_system
        }
        print(f"🔧 Отправка запроса choose-payment-system:")
        print(f"   URL: {url}")
        print(f"   Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
        print(f"   Headers: {dict(self.session.headers)}")
        try:
            response = self.session.post(url, json=payload)
            print(f"   Status Code: {response.status_code}")
            print(f"   Response Headers: {dict(response.headers)}")
            if response.status_code >= 400:
                print(f"   Response Text: {response.text[:500]}")
            result = response.json()
            print(f"   Response JSON: {json.dumps(result, ensure_ascii=False, indent=2)}")
            return result
        except requests.exceptions.HTTPError as e:
            print(f"❌ HTTP Error: {e}")
            if hasattr(e.response, 'text'):
                print(f"   Response Text: {e.response.text[:1000]}")
            raise
        except Exception as e:
            print(f"❌ Unexpected Error: {e}")
            raise
    def get_tinkoff_payment_url(self, payment_id: str) -> str:
        """
        Получить ссылку на оплату T-Bank
        Args:
            payment_id: ID платежа
        Returns:
            str: URL для оплаты
        """
        self.logger.info(f"🔗 get_tinkoff_payment_url: payment_id={payment_id}")
        url = f"{self.BASE_URL}/api/billing/payment/tinkoff/{payment_id}/payment-params"
        self.logger.info(f"📡 GET {url}")
        response = self.session.get(url)
        data = response.json()
        self.logger.debug(f"📦 Response JSON: {data}")
        # Tinkoff API возвращает PaymentURL в поле PaymentURL (PascalCase)
        payment_url = (
            data.get('PaymentURL') or
            data.get('payment_url') or
            data.get('url') or
            data.get('redirect_url') or
            data.get('link')
        )
        if not payment_url:
            import json
            # Если ссылки нет, возвращаем ошибку с полным ответом для отладки
            self.logger.error(f"❌ Не удалось найти payment URL в ответе: {json.dumps(data, ensure_ascii=False, indent=2)}")
            raise ValueError(f"Не удалось найти payment URL в ответе. Ответ: {json.dumps(data, ensure_ascii=False, indent=2)}")
        self.logger.info(f"✅ Payment URL получен: {payment_url}")
        return payment_url

    def create_payment_link(self, amount: int, currency: str = "RUB", 
                           payment_system: str = "bank-card") -> Dict:
        """
        Полный цикл создания платежной ссылки
        Args:
            amount: Сумма в рублях (в копейках: 25000 = 250 руб)
            currency: Валюта
            payment_system: Платежная система
                          - "bank-card" для "Банковская карта" (2% комиссия, прямой Tinkoff)
                          - "tinkoff" для "Тинькоф" (4% комиссия, через YooKassa)
        Returns:
            dict: Информация о платеже и ссылка
        """
        # 1. Создать платеж
        self.logger.info(f"📝 Создание платежа: {amount/100} {currency}")
        deposit_response = self.create_payment(amount, currency)
        # В ответе deposit есть два ID:
        # - "id": core payment_id (для choose-payment-system)
        # - "paymentId": финальный payment_id для конкретной платежной системы
        core_payment_id = deposit_response.get('id') or deposit_response.get('payment_id')
        final_payment_id = deposit_response.get('paymentId') or deposit_response.get('payment_id')
        if not core_payment_id:
            raise ValueError(f"Не удалось получить payment_id из ответа: {deposit_response}")
        self.logger.info(f"✅ Платеж создан: core_id={core_payment_id}, final_id={final_payment_id}")
        # 2. Промежуточный шаг: получить payment_params (как в браузере)
        # Это может быть необходимо для инициализации платежа, даже если возвращает 404
        import time
        self.logger.info(f"⏳ Задержка перед выбором платежной системы (5 сек для избежания rate limiting)...")
        time.sleep(5)
        try:
            self.logger.info(f"📋 Пробуем получить payment_params (может вернуть 404, это нормально)...")
            self.get_payment_params(core_payment_id)
        except Exception as e:
            # 404 нормально, продолжаем
            if "404" in str(e) or "Not Found" in str(e):
                self.logger.warning(f"⚠️  Payment params не найдены (это нормально, продолжаем)")
            else:
                self.logger.warning(f"⚠️  Ошибка получения payment_params: {e}")
        # 3. Выбрать платежную систему
        # ВАЖНО: Для choose-payment-system используем core_payment_id (id из deposit) в URL
        # Для "bank-card" (Банковская карта 2%) используем "tinkoff" как paymentSystem
        tinkoff_payment_id = None
        if payment_system == "bank-card":
            self.logger.info(f"🔧 Выбор платежной системы: tinkoff (для Банковская карта 2%)")
            self.logger.info(f"   Используем core_payment_id: {core_payment_id}")
            try:
                # Выбираем платежную систему используя core_payment_id
                # ВАЖНО: для choose-payment-system используем core_payment_id (id из deposit), а не final_payment_id
                choose_response = self.choose_payment_system(core_payment_id, "tinkoff")
                # Новый payment_id приходит в ответе: {"id": "новый-id", "paymentSystem": "tinkoff"}
                new_payment_id = choose_response.get("id")
                if new_payment_id:
                    self.logger.info(f"✅ Получен новый payment_id: {new_payment_id}")
                    tinkoff_payment_id = new_payment_id
                else:
                    self.logger.warning(f"⚠️  Не удалось получить payment_id из ответа, используем final_payment_id")
                    tinkoff_payment_id = final_payment_id
            except Exception as e:
                self.logger.error(f"⚠️  Ошибка при выборе платежной системы: {e}")
                self.logger.warning(f"⚠️  Пробуем использовать final_payment_id напрямую")
                tinkoff_payment_id = final_payment_id
        else:
            self.logger.info(f"🔧 Выбор платежной системы: {payment_system}")
            self.logger.info(f"   Используем core_payment_id: {core_payment_id}")
            try:
                choose_response = self.choose_payment_system(core_payment_id, payment_system)
                new_payment_id = choose_response.get("id") or final_payment_id
                tinkoff_payment_id = new_payment_id
            except Exception as e:
                self.logger.error(f"⚠️  Ошибка при выборе платежной системы: {e}")
                self.logger.warning(f"⚠️  Пробуем использовать final_payment_id напрямую")
                tinkoff_payment_id = final_payment_id
        if not tinkoff_payment_id:
            tinkoff_payment_id = final_payment_id
        # 4. Получить ссылку на оплату
        # Небольшая задержка после choose-payment-system для обработки на стороне ML Cloud
        import time
        self.logger.info(f"⏳ Задержка перед получением payment URL (2 сек)...")
        time.sleep(2)
        self.logger.info(f"🔗 Получение ссылки на оплату для payment_id: {tinkoff_payment_id}")
        # Для "bank-card" используем прямой путь к Tinkoff с новым payment_id
        if payment_system == "bank-card":
            # Банковская карта (2%): прямой путь к Tinkoff с новым payment_id
            payment_url = self.get_tinkoff_payment_url(tinkoff_payment_id)
        elif payment_system == "tinkoff":
            # Тинькоф (4%): через YooKassa
            url = f"{self.BASE_URL}/api/billing/payment/yookassa/{tinkoff_payment_id}/yookassa_tinkoff/payment-params"
            response = self.session.get(url)
            data = response.json()
            payment_url = data.get('payment_url') or data.get('url') or data.get('redirect_url') or data.get('link')
        else:
            # Для других платежных систем
            url = f"{self.BASE_URL}/api/billing/payment/{payment_system}/{tinkoff_payment_id}/payment-params"
            response = self.session.get(url)
            data = response.json()
            payment_url = data.get('payment_url') or data.get('url')
        if not payment_url:
            import json
            # Если ссылки нет, возвращаем ошибку с полным ответом для отладки
            raise ValueError(f"Не удалось найти payment URL в ответе. Ответ: {json.dumps(data, ensure_ascii=False, indent=2)}")
        self.logger.info(f"✅ Платежная ссылка создана: {payment_url}")
        return {
            'payment_id': core_payment_id,
            'amount': amount,
            'currency': currency,
            'payment_system': payment_system,
            'payment_url': payment_url,
            'deposit_response': deposit_response
        }
