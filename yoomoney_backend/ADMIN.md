# Админ-панель ЮMoney бэкенда

## Доступ к админ-панели

Админ-панель доступна по адресу: `http://your-server:5000/admin`

### Авторизация

Используется Basic Authentication. Учетные данные настраиваются в `.env`:
- `ADMIN_USERNAME` - имя пользователя (по умолчанию: `admin`)
- `ADMIN_PASSWORD` - пароль (по умолчанию: `admin`)

**⚠️ ВАЖНО:** Обязательно измените пароль по умолчанию в production!

## Возможности админ-панели

### 1. Главная страница (`/admin`)
- **Статистика:**
  - Всего донатов
  - Успешных донатов
  - Ожидающих донатов
  - Общая сумма

- **Таблица донатов:**
  - ID доната
  - Telegram ID пользователя
  - Сумма
  - Статус
  - Operation ID
  - Label
  - Дата и время

- **Функции:**
  - Поиск по Telegram ID
  - Обновление данных
  - Экспорт в CSV

### 2. API эндпоинты

#### `/admin/api/stats` (GET)
Получение статистики в JSON формате:
```json
{
  "total_donations": 150,
  "successful_donations": 145,
  "pending_donations": 5,
  "total_amount": 15000.50
}
```

#### `/admin/api/donations` (GET)
Получение списка донатов:
- `limit` - количество записей (по умолчанию: 100)
- `offset` - смещение (по умолчанию: 0)
- `telegram_id` - фильтр по Telegram ID

Пример: `/admin/api/donations?limit=50&telegram_id=123456789`

#### `/admin/export` (GET)
Экспорт всех донатов в CSV файл.

#### `/admin/config` (GET)
Просмотр конфигурации (токены скрыты для безопасности).

## Настройка

Добавьте в `.env`:
```env
ADMIN_USERNAME=your_username
ADMIN_PASSWORD=your_secure_password
```

## Безопасность

1. **Измените пароль по умолчанию!**
2. Используйте HTTPS в production
3. Ограничьте доступ к админ-панели через firewall
4. Регулярно проверяйте логи

## Пример использования API

```python
import requests
from requests.auth import HTTPBasicAuth

# Получение статистики
response = requests.get(
    'http://your-server:5000/admin/api/stats',
    auth=HTTPBasicAuth('admin', 'password')
)
stats = response.json()

# Получение донатов пользователя
response = requests.get(
    'http://your-server:5000/admin/api/donations?telegram_id=123456789',
    auth=HTTPBasicAuth('admin', 'password')
)
donations = response.json()
```

