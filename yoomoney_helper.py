"""Helper модуль для работы с YooMoney API используя библиотеку yoomoney"""
import logging
from urllib.parse import urlencode
from typing import Optional, Dict, Any
from datetime import datetime
from yoomoney import Client, Quickpay

logger = logging.getLogger(__name__)


class YooMoneyHelper:
    """Helper класс для упрощения работы с YooMoney API"""
    
    def __init__(self, client_id: str = None, client_secret: str = None, 
                 redirect_uri: str = None, wallet: str = None, token: str = None):
        """
        Инициализация helper'а
        
        Args:
            client_id: ID клиента YooMoney
            client_secret: Секретный ключ клиента
            redirect_uri: URI для редиректа после OAuth
            wallet: Номер кошелька YooMoney
            token: Токен доступа (если уже получен)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.wallet = wallet
        self.token = token
        self._client = None
    
    @property
    def client(self) -> Optional[Client]:
        """Получить клиент YooMoney"""
        if self.token and not self._client:
            self._client = Client(token=self.token)
        return self._client
    
    def get_oauth_url(self, scope: list = None) -> str:
        """
        Получить URL для OAuth авторизации
        
        Args:
            scope: Список разрешений (по умолчанию: account-info, operation-history, payment-p2p)
        
        Returns:
            URL для редиректа на авторизацию
        """
        if not self.client_id or not self.redirect_uri:
            raise ValueError("client_id and redirect_uri are required for OAuth")
        
        if scope is None:
            scope = ['account-info', 'operation-history', 'payment-p2p']
        
        scope_str = ' '.join(scope)
        
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'scope': scope_str
        }
        
        auth_url = f"https://yoomoney.ru/oauth/authorize?{urlencode(params)}"
        return auth_url
    
    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Обменять код авторизации на токен доступа
        
        Args:
            code: Код авторизации от YooMoney
        
        Returns:
            Словарь с информацией о токене
        """
        if not self.client_id or not self.redirect_uri:
            raise ValueError("client_id and redirect_uri are required")
        
        import requests
        
        token_data = {
            'code': code,
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        # CLIENT_SECRET опционален (может не быть настроен)
        if self.client_secret:
            token_data['client_secret'] = self.client_secret
        
        response = requests.post('https://yoomoney.ru/oauth/token', data=token_data)
        response.raise_for_status()
        
        token_info = response.json()
        
        # Обновляем токен если получен и пытаемся получить номер кошелька
        if 'access_token' in token_info:
            self.token = token_info['access_token']
            self._client = None  # Сброс клиента для пересоздания с новым токеном
            
            # Пытаемся получить номер кошелька через API
            try:
                account_info = self.get_account_info()
                if account_info and hasattr(account_info, 'account'):
                    self.wallet = account_info.account
                    logger.info(f"Wallet number obtained after token exchange: {self.wallet[:3]}***")
            except Exception as e:
                logger.warning(f"Could not get wallet number after token exchange: {e}")
        
        return token_info
    
    def generate_quickpay_url(self, amount: float, label: str, 
                             description: str = None, payment_type: str = 'AC',
                             success_url: str = None, wallet: str = None) -> str:
        """
        Генерация URL для быстрой оплаты через QuickPay используя библиотеку yoomoney
        
        Args:
            amount: Сумма платежа
            label: Уникальный идентификатор платежа
            description: Описание платежа
            payment_type: Тип оплаты ('AC' - карта, 'PC' - кошелек, 'MC' - телефон)
            success_url: URL для редиректа после успешной оплаты
            wallet: Номер кошелька (обязателен для QuickPay)
        
        Returns:
            URL для оплаты
        """
        # Используем переданный wallet или сохраненный
        wallet_number = wallet or self.wallet
        
        # Если нет wallet, пытаемся получить через API (если есть токен)
        if not wallet_number and self.client:
            try:
                account_info = self.get_account_info()
                if account_info and hasattr(account_info, 'account'):
                    wallet_number = account_info.account
                    self.wallet = wallet_number  # Сохраняем для будущего использования
                    logger.info(f"Wallet number obtained from API: {wallet_number[:3]}***")
            except Exception as e:
                logger.warning(f"Could not get wallet from API: {e}")
        
        if not wallet_number:
            raise ValueError(
                "Wallet number (receiver) is required for QuickPay. "
                "Please configure YMONEY_WALLET in settings or authorize via OAuth to get it automatically."
            )
        
        # Проверяем, что wallet не является плейсхолдером
        if wallet_number == "your_wallet_number_here" or "your_wallet" in wallet_number.lower():
            raise ValueError(
                f"Invalid wallet number: {wallet_number}. "
                "Please configure YMONEY_WALLET with your actual YooMoney wallet number."
            )
        
        if description is None:
            description = "Оплата"
        
        # Используем библиотеку Quickpay напрямую для генерации URL
        try:
            quickpay = Quickpay(
                receiver=wallet_number,
                quickpay_form='button',
                targets=description,
                paymentType=payment_type,
                sum=amount,
                label=label,
                formcomment=description if description else None,
                short_dest=description if description else None,
                successURL=success_url if success_url else None
            )
            
            # Библиотека Quickpay делает POST запрос и возвращает redirected_url
            # Но нам нужен просто URL, поэтому формируем его вручную используя те же параметры
            # что и библиотека
            params = {
                'receiver': wallet_number,
                'quickpay-form': 'button',
                'targets': description,
                'paymentType': payment_type,
                'sum': str(amount),
                'label': label
            }
            
            if description:
                params['formcomment'] = description
                params['short-dest'] = description
            
            if success_url:
                params['successURL'] = success_url
            
            # Формируем URL для GET запроса (QuickPay работает через confirm без .xml)
            base_url = "https://yoomoney.ru/quickpay/confirm?"
            url = base_url + urlencode(params)
            
            logger.info(f"Generated QuickPay URL for wallet: {wallet_number[:3]}***")
            return url
            
        except Exception as e:
            logger.error(f"Error creating Quickpay object: {e}", exc_info=True)
            # Fallback: формируем URL вручную
            params = {
                'receiver': wallet_number,
                'quickpay-form': 'button',
                'targets': description,
                'paymentType': payment_type,
                'sum': str(amount),
                'label': label
            }
            
            if description:
                params['formcomment'] = description
                params['short-dest'] = description
            
            if success_url:
                params['successURL'] = success_url
            
            base_url = "https://yoomoney.ru/quickpay/confirm?"
            url = base_url + urlencode(params)
            return url
    
    def get_account_info(self) -> Optional[Any]:
        """
        Получить информацию об аккаунте
        
        Returns:
            Информация об аккаунте или None если токен не установлен
        """
        if not self.client:
            logger.warning("Token not set, cannot get account info")
            return None
        
        try:
            return self.client.account_info()
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
        Получить историю операций через API YooMoney
        
        Согласно документации API YooMoney (https://yoomoney.ru/document/api-koshelka):
        - type: Тип операции ('deposition' - поступления, 'payment' - платежи, 'incoming' - входящие, 'outgoing' - исходящие)
        - label: Фильтр по метке платежа
        - from: Дата начала периода (формат: YYYY-MM-DDTHH:MM:SS)
        - till: Дата окончания периода (формат: YYYY-MM-DDTHH:MM:SS)
        - records: Количество записей (по умолчанию 30, максимум 100)
        - start_record: Номер первой записи (для пагинации)
        
        Args:
            label: Фильтр по label платежа
            operation_type: Тип операции ('deposition', 'payment', 'incoming', 'outgoing')
            from_date: Дата начала периода поиска
            till_date: Дата окончания периода поиска
            records: Количество записей для получения (максимум 100)
            start_record: Номер первой записи (для пагинации)
            **kwargs: Дополнительные параметры
        
        Returns:
            История операций или None если токен не установлен
        """
        if not self.client:
            logger.warning("Token not set, cannot get operation history")
            return None
        
        try:
            # Формируем параметры запроса
            params = {}
            
            if label:
                params['label'] = label
            
            if operation_type:
                params['type'] = operation_type
            
            if from_date:
                # Преобразуем datetime в формат YYYY-MM-DDTHH:MM:SS
                if isinstance(from_date, datetime):
                    params['from'] = from_date.strftime('%Y-%m-%dT%H:%M:%S')
                else:
                    params['from'] = from_date
            
            if till_date:
                # Преобразуем datetime в формат YYYY-MM-DDTHH:MM:SS
                if isinstance(till_date, datetime):
                    params['till'] = till_date.strftime('%Y-%m-%dT%H:%M:%S')
                else:
                    params['till'] = till_date
            
            if records:
                params['records'] = min(records, 100)  # Максимум 100 записей за раз
            
            if start_record:
                params['start_record'] = start_record
            
            # Добавляем дополнительные параметры
            params.update(kwargs)
            
            logger.debug(f"Requesting operation history with params: {params}")
            
            # Вызываем метод библиотеки
            return self.client.operation_history(**params)
        except Exception as e:
            logger.error(f"Error getting operation history: {e}", exc_info=True)
            return None
    
    def get_operation_details(self, operation_id: str) -> Optional[Any]:
        """
        Получить детали операции
        
        Args:
            operation_id: ID операции
        
        Returns:
            Детали операции или None если токен не установлен
        """
        if not self.client:
            logger.warning("Token not set, cannot get operation details")
            return None
        
        try:
            return self.client.operation_details(operation_id)
        except Exception as e:
            logger.error(f"Error getting operation details: {e}", exc_info=True)
            return None
    
    def verify_payment_by_label(self, label: str, days_back: int = 30) -> Optional[Dict[str, Any]]:
        """
        Проверить платеж по label через API YooMoney
        
        Args:
            label: Уникальный label платежа
            days_back: За сколько дней назад искать платеж (по умолчанию 30)
        
        Returns:
            Словарь с информацией о платеже или None если не найден
            Формат: {
                'found': bool,
                'operation_id': str,
                'amount': float,
                'currency': str,
                'datetime': datetime,
                'status': str,  # 'success', 'pending', 'failed'
                'operation': Any  # Объект операции от API
            }
        """
        if not self.client:
            logger.warning("Token not set, cannot verify payment")
            return None
        
        try:
            from datetime import datetime, timedelta
            
            # Получаем историю операций за последние N дней
            from_date = datetime.now() - timedelta(days=days_back)
            
            logger.info(f"Searching for payment with label: {label} in operations from {from_date}")
            
            # Получаем историю операций с фильтром по label
            # Используем тип 'deposition' для получения только входящих платежей
            history = self.get_operation_history(
                label=label,
                operation_type='deposition',  # Только поступления (входящие платежи)
                from_date=from_date
            )
            
            if not history or not hasattr(history, 'operations'):
                logger.info(f"No operations found for label: {label}")
                return {'found': False}
            
            # Ищем операцию с нужным label
            for operation in history.operations:
                if hasattr(operation, 'label') and operation.label == label:
                    # Проверяем тип операции (должна быть входящей)
                    if hasattr(operation, 'direction') and operation.direction == 'in':
                        # Определяем статус
                        status = 'success'
                        if hasattr(operation, 'status') and operation.status:
                            if operation.status == 'success':
                                status = 'success'
                            elif operation.status == 'pending':
                                status = 'pending'
                            else:
                                status = 'failed'
                        
                        result = {
                            'found': True,
                            'operation_id': operation.operation_id if hasattr(operation, 'operation_id') else None,
                            'amount': float(operation.amount) if hasattr(operation, 'amount') else 0.0,
                            'currency': operation.amount.currency if hasattr(operation, 'amount') and hasattr(operation.amount, 'currency') else 'RUB',
                            'datetime': operation.datetime if hasattr(operation, 'datetime') else None,
                            'status': status,
                            'operation': operation
                        }
                        
                        logger.info(f"Payment found: operation_id={result['operation_id']}, amount={result['amount']}, status={status}")
                        return result
            
            logger.info(f"Payment with label {label} not found in operations")
            return {'found': False}
            
        except Exception as e:
            logger.error(f"Error verifying payment by label: {e}", exc_info=True)
            return None
    
    def verify_payment_by_operation_id(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """
        Проверить платеж по operation_id через API YooMoney
        
        Args:
            operation_id: ID операции в YooMoney
        
        Returns:
            Словарь с информацией о платеже или None если не найден
        """
        if not self.client:
            logger.warning("Token not set, cannot verify payment")
            return None
        
        try:
            operation = self.client.operation_details(operation_id)
            
            if not operation:
                return {'found': False}
            
            # Определяем статус
            status = 'success'
            if hasattr(operation, 'status') and operation.status:
                if operation.status == 'success':
                    status = 'success'
                elif operation.status == 'pending':
                    status = 'pending'
                else:
                    status = 'failed'
            
            result = {
                'found': True,
                'operation_id': operation_id,
                'amount': float(operation.amount) if hasattr(operation, 'amount') else 0.0,
                'currency': operation.amount.currency if hasattr(operation, 'amount') and hasattr(operation.amount, 'currency') else 'RUB',
                'datetime': operation.datetime if hasattr(operation, 'datetime') else None,
                'status': status,
                'label': operation.label if hasattr(operation, 'label') else None,
                'operation': operation
            }
            
            logger.info(f"Payment verified: operation_id={operation_id}, amount={result['amount']}, status={status}")
            return result
            
        except Exception as e:
            logger.error(f"Error verifying payment by operation_id: {e}", exc_info=True)
            return None
    
    def sync_pending_payments(self, payments: list, days_back: int = 30) -> Dict[str, Any]:
        """
        Синхронизировать список pending платежей с YooMoney API
        
        Args:
            payments: Список объектов Payment из БД со статусом 'pending'
            days_back: За сколько дней назад искать платежи
        
        Returns:
            Словарь со статистикой синхронизации:
            {
                'checked': int,
                'found': int,
                'updated': int,
                'errors': list
            }
        """
        if not self.client:
            logger.warning("Token not set, cannot sync payments")
            return {'checked': 0, 'found': 0, 'updated': 0, 'errors': ['Token not set']}
        
        stats = {
            'checked': 0,
            'found': 0,
            'updated': 0,
            'errors': []
        }
        
        for payment in payments:
            try:
                stats['checked'] += 1
                
                # Пробуем проверить по label
                if payment.yoomoney_label:
                    result = self.verify_payment_by_label(payment.yoomoney_label, days_back)
                    
                    if result and result.get('found'):
                        stats['found'] += 1
                        # Возвращаем результат для обновления в БД
                        payment._verification_result = result
                        stats['updated'] += 1
                        logger.info(f"Payment {payment.id} (label: {payment.yoomoney_label}) found in YooMoney")
                
                # Если есть operation_id, проверяем и по нему
                elif payment.yoomoney_payment_id:
                    result = self.verify_payment_by_operation_id(payment.yoomoney_payment_id)
                    
                    if result and result.get('found'):
                        stats['found'] += 1
                        payment._verification_result = result
                        stats['updated'] += 1
                        logger.info(f"Payment {payment.id} (operation_id: {payment.yoomoney_payment_id}) found in YooMoney")
                
            except Exception as e:
                error_msg = f"Error syncing payment {payment.id}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                stats['errors'].append(error_msg)
        
        logger.info(f"Payment sync completed: checked={stats['checked']}, found={stats['found']}, updated={stats['updated']}, errors={len(stats['errors'])}")
        return stats
    
    def get_all_incoming_payments(self, from_date: datetime = None, 
                                  till_date: datetime = None,
                                  max_records: int = 1000) -> Optional[Dict[str, Any]]:
        """
        Получить все входящие платежи за период через API YooMoney
        
        Согласно документации API YooMoney:
        - Использует тип 'deposition' для получения только поступлений (входящих платежей)
        - Поддерживает пагинацию (максимум 100 записей за один запрос)
        - Автоматически обрабатывает несколько страниц для получения всех записей
        
        Args:
            from_date: Дата начала периода (если None, то за последние 30 дней)
            till_date: Дата окончания периода (если None, то текущая дата)
            max_records: Максимальное количество записей для получения (по умолчанию 1000)
        
        Returns:
            Словарь с результатами:
            {
                'operations': list,  # Список всех операций
                'total_count': int,  # Общее количество полученных операций
                'next_record': int   # Номер следующей записи (если есть еще данные)
            }
        """
        if not self.client:
            logger.warning("Token not set, cannot get incoming payments")
            return None
        
        try:
            from datetime import timedelta
            
            # Устанавливаем период по умолчанию
            if not from_date:
                from_date = datetime.now() - timedelta(days=30)
            if not till_date:
                till_date = datetime.now()
            
            all_operations = []
            start_record = 0
            records_per_request = 100  # Максимум за один запрос
            total_fetched = 0
            
            logger.info(f"Fetching incoming payments from {from_date} to {till_date}")
            
            # Получаем данные постранично
            while total_fetched < max_records:
                # Определяем, сколько записей запросить в этом запросе
                records_to_fetch = min(records_per_request, max_records - total_fetched)
                
                # Получаем историю операций
                history = self.get_operation_history(
                    operation_type='deposition',  # Только входящие платежи (поступления)
                    from_date=from_date,
                    till_date=till_date,
                    records=records_to_fetch,
                    start_record=start_record
                )
                
                if not history or not hasattr(history, 'operations'):
                    logger.info("No more operations found")
                    break
                
                # Добавляем операции в общий список
                operations_batch = list(history.operations) if history.operations else []
                all_operations.extend(operations_batch)
                
                total_fetched += len(operations_batch)
                logger.debug(f"Fetched {len(operations_batch)} operations (total: {total_fetched})")
                
                # Проверяем, есть ли еще данные
                if hasattr(history, 'next_record') and history.next_record:
                    start_record = history.next_record
                elif len(operations_batch) < records_to_fetch:
                    # Если получили меньше записей, чем запрашивали, значит это последняя страница
                    break
                else:
                    # Переходим к следующей странице
                    start_record += len(operations_batch)
                
                # Если получили меньше записей, чем запрашивали, значит больше нет данных
                if len(operations_batch) == 0:
                    break
            
            result = {
                'operations': all_operations,
                'total_count': len(all_operations),
                'next_record': start_record if total_fetched >= max_records else None
            }
            
            logger.info(f"Successfully fetched {len(all_operations)} incoming payments")
            return result
            
        except Exception as e:
            logger.error(f"Error getting all incoming payments: {e}", exc_info=True)
            return None

