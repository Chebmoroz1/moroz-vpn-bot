# Процесс разработки VPN Bot

## 🎯 Философия разработки

Система разделена на две части:
1. **Код (статический)** - логика, функционал, интерфейс
2. **Конфигурация (динамическая)** - секреты, ключи API, настройки

## 📊 Разделение ответственности

### Что менять в коде (локально + деплой на VPS)

✅ **Безопасно для параллельной разработки:**
- Логика бота (`bot.py`)
- Обработчики команд и callback'ов
- UI/UX элементы (кнопки, меню)
- Бизнес-логика создания VPN ключей
- Валидация данных
- Новые функции и возможности
- Исправление багов
- Улучшения производительности

✅ **Файлы для изменений:**
- `bot.py` - основная логика бота
- `vpn_manager.py` - управление VPN
- `contacts.py` - управление контактами
- `database.py` - модели БД (структура)
- `web_server.py`, `yoomoney_backend.py` - веб-серверы
- `deploy/` - скрипты развертывания

### Что настраивать через админ-панель (только на VPS)

🔐 **Динамические настройки (из БД):**
- `YMONEY_CLIENT_ID` - ID приложения YooMoney
- `YMONEY_CLIENT_SECRET` - Секретный ключ YooMoney
- `YMONEY_WALLET` - Номер кошелька YooMoney
- `BOT_TOKEN` - Токен Telegram бота (если нужно менять)
- `WEB_SERVER_DOMAIN` - Домен для веб-сервера
- Любые другие секреты и ключи API

⚠️ **Важно:** Секретные данные НЕ должны быть в `.env` файле, который копируется на VPS. Они должны настраиваться через админ-панель.

## 🔄 Процесс разработки

### Шаг 1: Локальная разработка

```bash
# 1. Внесите изменения в код локально
# Например, добавили новую функцию в bot.py

# 2. Протестируйте локально
python bot.py

# 3. Убедитесь, что все работает
```

### Шаг 2: Развертывание кода на VPS

```bash
# 1. Запустите скрипт развертывания
cd /path/to/vpn-bot
./deploy/deploy.sh

# Скрипт автоматически:
# - Скопирует код на VPS (БЕЗ .env файла)
# - Обновит зависимости Python
# - Перезапустит сервисы
# - Сохранит все данные из БД
```

### Шаг 3: Настройка секретов через админ-панель

```bash
# 1. Откройте бота в Telegram
# 2. Перейдите в "⚙️ Админ-панель"
# 3. Выберите "⚙️ Настройки приложения"
# 4. Выберите категорию (Telegram, YooMoney, VPN, Общие)
# 5. Добавьте или отредактируйте настройки

# Настройки автоматически сохраняются в БД и используются приложением
```

## 🔐 Система хранения настроек

### Модель AppConfig (в БД)

```python
- key: str           # Ключ настройки (например, "YMONEY_CLIENT_ID")
- value: str         # Значение настройки
- description: str   # Описание настройки
- is_secret: bool    # Является ли секретом (скрывать в UI)
- category: str      # Категория (telegram, yoomoney, vpn, general)
```

### ConfigManager

```python
from config_manager import config_manager

# Получить значение
value = config_manager.get("YMONEY_CLIENT_ID", "default_value")

# Установить значение
config_manager.set("YMONEY_CLIENT_ID", "new_value", 
                   description="YooMoney Client ID",
                   is_secret=True, 
                   category="yoomoney")
```

### Интеграция с config.py

`config.py` теперь поддерживает приоритет:
1. БД (через config_manager) - **высший приоритет**
2. .env файл - fallback
3. Значение по умолчанию

```python
# В config.py
YMONEY_CLIENT_ID = config_manager.get("YMONEY_CLIENT_ID") or os.getenv("YMONEY_CLIENT_ID", "")
```

## 📝 Процесс развертывания

### Автоматическое развертывание (рекомендуется)

```bash
./deploy/deploy.sh
```

**Что делает скрипт:**
1. ✅ Копирует код (исключая `.env`, `.db`, `vpn_configs/`)
2. ✅ Устанавливает зависимости Python
3. ✅ Обновляет systemd сервисы
4. ✅ Перезапускает сервисы
5. ✅ **Сохраняет все данные из БД** (не перезаписывает)

### Ручное развертывание

```bash
# 1. Создайте бэкап БД на VPS
ssh root@194.26.27.31 "cp /opt/vpn-bot/database.db /opt/vpn-bot/database.db.backup"

# 2. Скопируйте код (без .env и БД)
rsync -avz --exclude='.env' --exclude='*.db' --exclude='vpn_configs/*' \
    ./ root@194.26.27.31:/opt/vpn-bot/

# 3. Установите зависимости
ssh root@194.26.27.31 "cd /opt/vpn-bot && pip3 install -r requirements.txt"

# 4. Запустите миграции (если нужно)
ssh root@194.26.27.31 "cd /opt/vpn-bot && python3 -c 'from database import init_db; init_db()'"

# 5. Перезапустите сервисы
ssh root@194.26.27.31 "systemctl restart vpn-bot.service vpn-yoomoney.service"
```

## 🚨 Важные правила

### ✅ ДЕЛАТЬ:

1. **Изменяйте код локально** и тестируйте перед деплоем
2. **Используйте админ-панель** для секретных данных
3. **Делайте бэкапы БД** перед большими изменениями
4. **Тестируйте миграции** на тестовой БД
5. **Используйте git** для версионирования кода

### ❌ НЕ ДЕЛАТЬ:

1. **Не храните секреты в `.env`**, который копируется на VPS
2. **Не перезаписывайте БД** при развертывании
3. **Не редактируйте код напрямую на VPS** (используйте деплой)
4. **Не коммитьте `.env` файлы** в git (добавьте в `.gitignore`)

## 🔧 Настройка через админ-панель

### Категории настроек:

#### 📱 Telegram
- `BOT_TOKEN` - Токен Telegram бота

#### 💳 YooMoney
- `YMONEY_CLIENT_ID` - ID приложения YooMoney
- `YMONEY_CLIENT_SECRET` - Секретный ключ YooMoney
- `YMONEY_WALLET` - Номер кошелька YooMoney
- `YMONEY_REDIRECT_URI` - Redirect URI для YooMoney
- `YMONEY_NOTIFICATION_URI` - Notification URI для YooMoney
- `YMONEY_SITE_URL` - URL сайта для YooMoney

#### 🔐 VPN
- `VPN_PROTOCOL` - Протокол VPN
- `VPN_PORT` - Порт VPN
- `VPN_NETWORK` - Сеть VPN
- `VPN_DOCKER_CONTAINER` - Docker контейнер VPN
- `VPN_INTERFACE` - Интерфейс VPN

#### 🌐 Общие
- `WEB_SERVER_DOMAIN` - Домен веб-сервера
- `WEB_SERVER_PORT` - Порт веб-сервера
- `WEB_SERVER_URL` - URL веб-сервера

### Как использовать:

1. **Через Telegram бота:**
   - Откройте бота
   - Перейдите в "⚙️ Админ-панель"
   - Выберите "⚙️ Настройки приложения"
   - Выберите категорию
   - Редактируйте или добавляйте настройки

2. **Программно:**
   ```python
   from config_manager import config_manager
   
   config_manager.set("YMONEY_CLIENT_ID", "your_client_id",
                      description="YooMoney Client ID",
                      is_secret=True,
                      category="yoomoney")
   ```

## 📚 Примеры использования

### Пример 1: Добавление новой функции

```python
# 1. Добавьте функцию в bot.py локально
async def _handle_new_feature(self, update, context, db_user):
    # Ваш код
    pass

# 2. Протестируйте локально
python bot.py

# 3. Разверните на VPS
./deploy/deploy.sh

# 4. Функция автоматически работает на VPS
```

### Пример 2: Изменение секрета

```python
# ❌ НЕ ДЕЛАТЬ:
# 1. Изменить .env файл
# 2. Скопировать на VPS

# ✅ ДЕЛАТЬ:
# 1. Открыть админ-панель в Telegram
# 2. Перейти в "⚙️ Настройки приложения"
# 3. Выбрать категорию (например, YooMoney)
# 4. Отредактировать настройку
# 5. Новое значение сразу применяется
```

### Пример 3: Обновление зависимостей

```bash
# 1. Обновите requirements.txt локально
echo "new-package==1.0.0" >> requirements.txt

# 2. Протестируйте локально
pip install -r requirements.txt
python bot.py

# 3. Разверните на VPS
./deploy/deploy.sh  # Скрипт автоматически установит зависимости
```

## 🔄 Миграции БД

При изменении структуры БД создавайте миграционные скрипты:

```python
# migrate_001_add_config_table.py
def migrate():
    # Ваш код миграции
    pass
```

Запускайте миграции через:
```bash
ssh root@194.26.27.31 "cd /opt/vpn-bot && python3 migrate_001_add_config_table.py"
```

## 📞 Поддержка

Если что-то пошло не так:
1. Проверьте логи: `journalctl -u vpn-bot.service -f`
2. Проверьте БД: `sqlite3 /opt/vpn-bot/database.db ".tables"`
3. Восстановите бэкап БД при необходимости
4. Откатите код до предыдущей версии через git

