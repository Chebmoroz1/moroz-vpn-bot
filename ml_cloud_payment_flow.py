#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Управление потоком оплаты с автоматической проверкой баланса
- Отслеживание перехода в окно оплаты
- Автоматическая проверка через 2 минуты
- Ручная проверка с отменой автоматической
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Callable
import sys
import os

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from ml_cloud_integration import MLCloudIntegration
    from ml_cloud_payment_tracker import MLCloudPaymentTracker
except ImportError:
    # Для случаев когда модули еще не скопированы
    MLCloudIntegration = None
    MLCloudPaymentTracker = None


class PaymentFlowState:
    """Состояние потока оплаты для пользователя"""
    
    def __init__(self, user_id: int, payment_id: str, amount: float):
        self.user_id = user_id
        self.payment_id = payment_id
        self.amount = amount
        self.link_sent_at = datetime.now()
        self.link_opened = False  # Определяется по нажатию кнопки
        self.auto_check_scheduled = False
        self.auto_check_task = None
        self.auto_check_cancelled = False
        self.checked_at = None
        self.payment_confirmed = False


class MLCloudPaymentFlow:
    """Управление потоком оплаты с проверкой баланса"""
    
    # Глобальный словарь для хранения состояний пользователей
    _user_states: Dict[int, PaymentFlowState] = {}
    
    def __init__(self):
        """Инициализация"""
        self.ml_cloud = MLCloudIntegration()
        self.tracker = MLCloudPaymentTracker()
        self.auto_check_delay = 120  # 2 минуты в секундах
    
    def create_payment_and_send_link(self, user_id: int, amount_rub: int, schedule_auto_check: bool = False) -> Dict:
        """
        Создать платежную ссылку для пользователя
        
        Args:
            user_id: ID пользователя Telegram
            amount_rub: Сумма в рублях
        
        Returns:
            dict: {
                'payment_url': ссылка на оплату,
                'payment_id': ID платежа,
                'amount_rub': сумма,
                'total_rub': итого с комиссией
            }
        """
        # Создаем платежную ссылку
        result = self.ml_cloud.create_payment_link(
            amount_rub=amount_rub,
            user_id=user_id
        )
        
        # Сохраняем состояние пользователя
        state = PaymentFlowState(
            user_id=user_id,
            payment_id=result['payment_id'],
            amount=result['amount_rub']
        )
        self._user_states[user_id] = state
        
        # Планируем автоматическую проверку через 2 минуты (только если есть event loop)
        if schedule_auto_check:
            try:
                self._schedule_auto_check(user_id)
            except RuntimeError as e:
                if "no running event loop" in str(e):
                    # Нет event loop (вызов из синхронного контекста Flask)
                    # Автоматическая проверка будет отключена
                    pass
                else:
                    raise
        
        return {
            'payment_url': result['payment_url'],
            'payment_id': result['payment_id'],
            'amount_rub': result['amount_rub'],
            'commission_rub': result['commission_rub'],
            'total_rub': result['total_rub']
        }
    
    def mark_link_opened(self, user_id: int) -> bool:
        """
        Отметить что пользователь открыл ссылку оплаты
        
        Это вызывается когда пользователь нажимает кнопку оплаты в Telegram
        (Telegram показывает диалог подтверждения - значит ссылка будет открыта)
        
        Args:
            user_id: ID пользователя
        
        Returns:
            bool: True если состояние найдено и обновлено
        """
        if user_id in self._user_states:
            self._user_states[user_id].link_opened = True
            return True
        return False
    
    def _schedule_auto_check(self, user_id: int):
        """Запланировать автоматическую проверку через 2 минуты"""
        
        if user_id not in self._user_states:
            return
        
        state = self._user_states[user_id]
        
        # Если уже запланирована - не планируем повторно
        if state.auto_check_scheduled:
            return
        
        state.auto_check_scheduled = True
        
        async def auto_check_task():
            """Задача автоматической проверки"""
            try:
                # Ждем 2 минуты
                await asyncio.sleep(self.auto_check_delay)
                
                # Проверяем не отменена ли проверка
                if user_id not in self._user_states:
                    return
                
                state = self._user_states[user_id]
                
                if state.auto_check_cancelled:
                    print(f"⏭️  Автоматическая проверка отменена для user_id={user_id}")
                    return
                
                if state.payment_confirmed:
                    print(f"✅ Платеж уже подтвержден для user_id={user_id}")
                    return
                
                # Проверяем платеж
                print(f"🔄 Автоматическая проверка платежа для user_id={user_id}")
                result = self._check_payment(user_id, is_manual=False)
                
            except asyncio.CancelledError:
                print(f"❌ Автоматическая проверка отменена для user_id={user_id}")
            except Exception as e:
                print(f"❌ Ошибка автоматической проверки: {e}")
        
        # Запускаем задачу
        state.auto_check_task = asyncio.create_task(auto_check_task())
    
    def _cancel_auto_check(self, user_id: int):
        """Отменить автоматическую проверку"""
        
        if user_id not in self._user_states:
            return
        
        state = self._user_states[user_id]
        
        if state.auto_check_scheduled and not state.auto_check_cancelled:
            state.auto_check_cancelled = True
            
            # Отменяем задачу если она еще выполняется
            if state.auto_check_task and not state.auto_check_task.done():
                state.auto_check_task.cancel()
            
            print(f"⏹️  Автоматическая проверка отменена для user_id={user_id}")
    
    def _check_payment(self, user_id: int, is_manual: bool = True) -> Dict:
        """
        Проверить платеж пользователя
        
        Args:
            user_id: ID пользователя
            is_manual: Ручная проверка (True) или автоматическая (False)
        
        Returns:
            dict: Результат проверки
        """
        if user_id not in self._user_states:
            return {
                'found': False,
                'error': 'Payment not found'
            }
        
        state = self._user_states[user_id]
        
        # Если это ручная проверка - отменяем автоматическую
        if is_manual:
            self._cancel_auto_check(user_id)
        
        # Проверяем статус платежа
        status = self.tracker.check_payment_status(state.payment_id)
        
        if status['found']:
            # Платеж найден!
            state.payment_confirmed = True
            state.checked_at = datetime.now()
            
            # Очищаем состояние после подтверждения
            # (можно оставить для истории)
            
            return {
                'found': True,
                'confirmed': True,
                'amount': status['amount'],
                'currency': status['currency'],
                'date': status.get('date'),
                'is_manual': is_manual
            }
        else:
            # Платеж еще не найден
            return {
                'found': False,
                'confirmed': False,
                'is_manual': is_manual
            }
    
    def check_payment_manual(self, user_id: int) -> Dict:
        """
        Ручная проверка платежа пользователем
        
        Отменяет автоматическую проверку и проверяет сразу
        
        Args:
            user_id: ID пользователя
        
        Returns:
            dict: Результат проверки
        """
        return self._check_payment(user_id, is_manual=True)
    
    def get_user_state(self, user_id: int) -> Optional[PaymentFlowState]:
        """Получить состояние потока оплаты для пользователя"""
        return self._user_states.get(user_id)
    
    def should_show_check_button(self, user_id: int) -> bool:
        """
        Определить нужно ли показывать кнопку "Проверить баланс"
        
        Args:
            user_id: ID пользователя
        
        Returns:
            bool: True если нужно показывать кнопку проверки
        """
        if user_id not in self._user_states:
            return False
        
        state = self._user_states[user_id]
        
        # Показываем кнопку если:
        # 1. Ссылка была отправлена
        # 2. Платеж еще не подтвержден
        # 3. Прошло меньше 30 минут с момента отправки ссылки
        
        if state.payment_confirmed:
            return False
        
        time_since_link = datetime.now() - state.link_sent_at
        if time_since_link.total_seconds() > 1800:  # 30 минут
            return False
        
        return True
    
    def clear_user_state(self, user_id: int):
        """Очистить состояние пользователя"""
        if user_id in self._user_states:
            # Отменяем автоматическую проверку
            self._cancel_auto_check(user_id)
            # Удаляем состояние
            del self._user_states[user_id]
    
    def cleanup_old_states(self, max_age_minutes: int = 60):
        """Очистить старые состояния (старше N минут)"""
        now = datetime.now()
        
        users_to_remove = []
        
        for user_id, state in self._user_states.items():
            age = now - state.link_sent_at
            
            # Удаляем если старше max_age_minutes и платеж не подтвержден
            if age.total_seconds() > max_age_minutes * 60 and not state.payment_confirmed:
                users_to_remove.append(user_id)
        
        for user_id in users_to_remove:
            self.clear_user_state(user_id)


# Глобальный экземпляр для использования в боте
payment_flow = MLCloudPaymentFlow()


def get_payment_flow():
    """Получить глобальный экземпляр payment flow"""
    return payment_flow

