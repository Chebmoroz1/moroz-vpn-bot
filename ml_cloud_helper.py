#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML Cloud Helper - аналог YooMoneyHelper
Интеграция ML Cloud платежей для замены YooMoney
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from ml_cloud_integration import MLCloudIntegration
from ml_cloud_payment_flow import get_payment_flow

logger = logging.getLogger(__name__)

# Глобальный экземпляр для использования в боте
_ml_cloud_helper = None


class MLCloudHelper:
    """
    Helper для работы с ML Cloud (аналог YooMoneyHelper)
    Используется для замены YooMoney на ML Cloud платежи
    """
    
    MIN_AMOUNT = 250.0  # Минимальная сумма в рублях
    COMMISSION_PERCENT = 2  # Комиссия 2%
    
    def __init__(self):
        """Инициализация ML Cloud Helper"""
        try:
            self.ml_cloud = MLCloudIntegration()
            self.payment_flow = get_payment_flow()
            logger.info("MLCloudHelper инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации MLCloudHelper: {e}")
            raise
    
    def generate_quickpay_url(self, amount: float, label: str, 
                             description: str = None, 
                             payment_type: str = "AC",
                             success_url: Optional[str] = None,
                             user_id: Optional[int] = None) -> str:
        """
        Создать платежную ссылку через ML Cloud (Tinkoff)
        
        Аналог метода YooMoneyHelper.generate_quickpay_url()
        
        Args:
            amount: Сумма в рублях (минимум 250)
            label: Уникальный идентификатор платежа (для отслеживания)
            description: Описание платежа
            payment_type: Тип платежа (не используется, оставлен для совместимости)
            success_url: URL для редиректа после оплаты (опционально)
            user_id: ID пользователя Telegram (опционально)
        
        Returns:
            str: URL для оплаты через Tinkoff
        
        Raises:
            ValueError: Если сумма меньше минимальной
        """
        # Проверяем минимальную сумму
        amount_rub = float(amount)
        
        if amount_rub < self.MIN_AMOUNT:
            raise ValueError(
                f"Минимальная сумма платежа: {self.MIN_AMOUNT} рублей. "
                f"Указано: {amount_rub} рублей. "
                f"Комиссия {self.COMMISSION_PERCENT}% включена."
            )
        
        # Получаем user_id из label если не указан
        if not user_id and label:
            # Пытаемся извлечь user_id из label
            # Например: "donation_123456" или "user_12345"
            try:
                parts = label.split('_')
                if len(parts) >= 2 and parts[-1].isdigit():
                    user_id = int(parts[-1])
            except:
                pass
        
        try:
            # Создаем платежную ссылку через ML Cloud
            result = self.payment_flow.create_payment_and_send_link(schedule_auto_check=False, 
                user_id=user_id,
                amount_rub=int(amount_rub)
            )
            
            payment_url = result['payment_url']
            
            logger.info(
                f"Generated ML Cloud payment URL: amount={amount_rub}, "
                f"label={label}, payment_id={result['payment_id']}"
            )
            
            return payment_url
            
        except ValueError as e:
            logger.error(f"Validation error generating payment URL: {e}")
            raise
        except Exception as e:
            logger.error(f"Error generating ML Cloud payment URL: {e}", exc_info=True)
            raise
    
    def verify_payment_by_label(self, label: str, days_back: int = 30) -> Optional[Dict[str, Any]]:
        """
        Проверить платеж по label (для совместимости с YooMoneyHelper)
        
        В ML Cloud нет label, используем payment_id или ищем по сумме
        
        Args:
            label: Идентификатор платежа
            days_back: За сколько дней искать (не используется напрямую)
        
        Returns:
            dict: Данные платежа или None
        """
        # В ML Cloud нет label, нужно хранить mapping label -> payment_id
        # Пока возвращаем None - нужно будет доработать
        
        logger.warning(f"verify_payment_by_label called with label={label}, "
                      f"but ML Cloud doesn't use labels. Need to implement mapping.")
        
        return None
    
    def verify_payment_by_payment_id(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """
        Проверить платеж по payment_id
        
        Args:
            payment_id: ID платежа ML Cloud
        
        Returns:
            dict: Данные платежа или None
        """
        try:
            from ml_cloud_payment_tracker import MLCloudPaymentTracker
            
            tracker = MLCloudPaymentTracker()
            status = tracker.check_payment_status(payment_id)
            
            if status['found']:
                return {
                    'status': status['status'],
                    'amount': status['amount'],
                    'currency': status['currency'],
                    'date': status.get('date'),
                    'payment_id': payment_id
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error verifying payment by payment_id: {e}", exc_info=True)
            return None
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Получить информацию об аккаунте ML Cloud
        
        Returns:
            dict: Информация об аккаунте или None
        """
        try:
            # Получаем баланс через ML Cloud API
            token = self.ml_cloud.token_manager.auto_refresh_if_needed()
            
            import requests
            url = "https://app.ml.cloud/api/balance/my/new"
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            return {
                'balance': data.get('balance', {}).get('amount', 0),
                'currency': data.get('balance', {}).get('currency', 'RUB'),
                'account': 'ml_cloud'
            }
            
        except Exception as e:
            logger.error(f"Error getting account info: {e}", exc_info=True)
            return None
    
    def get_operation_history(self, label: str = None,
                             operation_type: str = None,
                             from_date: datetime = None,
                             till_date: datetime = None,
                             records: int = 30,
                             start_record: int = 0,
                             **kwargs) -> Optional[Any]:
        """
        Получить историю операций (для совместимости с YooMoneyHelper)
        
        Args:
            label: Фильтр по label (не используется в ML Cloud)
            operation_type: Тип операции
            from_date: Дата начала
            till_date: Дата окончания
            records: Количество записей
            start_record: Смещение
        
        Returns:
            list: Список платежей
        """
        try:
            from ml_cloud_payment_history import MLCloudPaymentHistory
            
            parser = MLCloudPaymentHistory()
            history = parser.get_history(limit=records, offset=start_record)
            
            # Фильтруем по датам если указаны
            if from_date or till_date:
                filtered = []
                for payment in history:
                    date_str = payment.get('date', '')
                    if date_str:
                        try:
                            if 'T' in date_str:
                                payment_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            else:
                                payment_date = datetime.strptime(date_str, '%d.%m.%Y %H:%M')
                            
                            if from_date and payment_date < from_date:
                                continue
                            if till_date and payment_date > till_date:
                                continue
                            
                            filtered.append(payment)
                        except:
                            pass
                
                return filtered
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting operation history: {e}", exc_info=True)
            return None
    
    def get_all_incoming_payments(self, from_date: datetime = None,
                                  max_records: int = 1000) -> Optional[Dict[str, Any]]:
        """
        Получить все входящие платежи (пополнения)
        
        Args:
            from_date: Дата начала периода
            max_records: Максимальное количество записей
        
        Returns:
            dict: Результаты поиска
        """
        try:
            from ml_cloud_payment_history import MLCloudPaymentHistory
            
            parser = MLCloudPaymentHistory()
            
            # Получаем только пополнения (положительные суммы)
            deposits = parser.get_deposits_only(limit=max_records)
            
            # Фильтруем по дате если указана
            if from_date:
                filtered = []
                for payment in deposits:
                    date_str = payment.get('date', '')
                    if date_str:
                        try:
                            if 'T' in date_str:
                                payment_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            else:
                                payment_date = datetime.strptime(date_str, '%d.%m.%Y %H:%M')
                            
                            if payment_date >= from_date:
                                filtered.append(payment)
                        except:
                            pass
                
                deposits = filtered
            
            return {
                'operations': deposits,
                'total': len(deposits)
            }
            
        except Exception as e:
            logger.error(f"Error getting incoming payments: {e}", exc_info=True)
            return None


def get_ml_cloud_helper() -> MLCloudHelper:
    """Получить глобальный экземпляр MLCloudHelper"""
    global _ml_cloud_helper
    
    if _ml_cloud_helper is None:
        _ml_cloud_helper = MLCloudHelper()
    
    return _ml_cloud_helper

