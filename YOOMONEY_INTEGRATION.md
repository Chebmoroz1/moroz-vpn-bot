# Интеграция библиотеки YooMoney

В проект интегрирована официальная библиотека `yoomoney` (версия 0.1.2) для упрощения работы с API YooMoney.

## Установка

Библиотека уже добавлена в `requirements.txt`:

```bash
pip install -r requirements.txt
```

Или установить отдельно:

```bash
pip install yoomoney==0.1.2
```

## Структура интеграции

### 1. Helper модуль (`yoomoney_helper.py`)

Создан helper класс `YooMoneyHelper`, который упрощает работу с API YooMoney:

- **OAuth авторизация**: генерация URL и обмен кода на токен
- **QuickPay**: генерация URL для быстрой оплаты
- **Работа с API**: получение информации об аккаунте, истории операций

### 2. Рефакторинг `yoomoney_backend.py`

Код упрощен за счет использования helper модуля:

- `yoomoney_auth()` - использует `helper.get_oauth_url()`
- `yoomoney_redirect()` - использует `helper.exchange_code_for_token()`
- `generate_payment_uri()` - использует `helper.generate_quickpay_url()`

## Использование

### Инициализация

```python
from yoomoney_helper import YooMoneyHelper

helper = YooMoneyHelper(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    redirect_uri="https://yourdomain.com/yoomoney_redirect",
    wallet="YOUR_WALLET_NUMBER"
)
```

### Генерация OAuth URL

```python
auth_url = helper.get_oauth_url()
# Редирект пользователя на auth_url
```

### Обмен кода на токен

```python
token_info = helper.exchange_code_for_token(code)
access_token = token_info['access_token']
```

### Генерация платежного URL

```python
payment_url = helper.generate_quickpay_url(
    amount=100.0,
    label="unique_payment_label",
    description="Оплата VPN",
    payment_type='AC',  # AC - карта, PC - кошелек, MC - телефон
    success_url="https://yourdomain.com/success"
)
```

### Работа с API (если токен установлен)

```python
# Установить токен
helper.token = "your_access_token"

# Получить информацию об аккаунте
account_info = helper.get_account_info()

# Получить историю операций
history = helper.get_operation_history(label="payment_label")

# Получить детали операции
details = helper.get_operation_details(operation_id="12345")
```

## Преимущества

1. **Упрощение кода**: меньше ручного формирования URL и обработки запросов
2. **Единая точка входа**: все операции через один helper класс
3. **Типизация**: использование официальной библиотеки обеспечивает совместимость с API
4. **Расширяемость**: легко добавить новые методы работы с API

## Зависимости

Библиотека `yoomoney` зависит от:
- `requests` - для HTTP запросов (уже в requirements.txt)

## Дополнительная информация

- [Библиотека на PyPI](https://pypi.org/project/YooMoney/)
- [GitHub репозиторий](https://github.com/AlekseyKorshuk/yoomoney-api)
- [Документация API YooMoney](https://yoomoney.ru/docs/wallet)

