# Развертывание VPN Bot на VPS

## 📋 Требования

- VPS сервер с Ubuntu/Debian
- Python 3.9+
- SSH доступ к серверу
- Домен, указывающий на VPS (для YooMoney)
- Nginx (опционально, для reverse proxy)

## 🚀 Быстрое развертывание

### 1. Подготовка локальной машины

Убедитесь, что у вас есть:
- SSH ключ для доступа к VPS
- Файл `.env` с правильными настройками
- Все зависимости установлены локально

### 2. Настройка переменных окружения

Скопируйте `.env.example` в `.env` и заполните:

```bash
cp .env.example .env
nano .env
```

Обязательные параметры:
```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_id
SERVER_HOST=194.26.27.31
WEB_SERVER_DOMAIN=moroz.myftp.biz
YMONEY_CLIENT_ID=your_yoomoney_client_id
YMONEY_CLIENT_SECRET=your_yoomoney_client_secret
YMONEY_WALLET=your_yoomoney_wallet
```

### 3. Автоматическое развертывание

Запустите скрипт развертывания:

```bash
cd /path/to/vpn-bot
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

Скрипт выполнит:
- ✅ Копирование файлов на VPS
- ✅ Установку зависимостей Python
- ✅ Создание systemd сервисов
- ✅ Настройку автозапуска
- ✅ Инициализацию базы данных
- ✅ Запуск сервисов

### 4. Настройка переменных окружения (опционально)

Если хотите изменить параметры развертывания:

```bash
export VPS_USER=root
export VPS_HOST=194.26.27.31
export VPS_APP_DIR=/opt/vpn-bot
export SSH_KEY=~/.ssh/id_ed25519
./deploy/deploy.sh
```

## 📝 Ручное развертывание

### 1. Подключение к VPS

```bash
ssh root@194.26.27.31
```

### 2. Создание пользователя (опционально, для безопасности)

```bash
# Создаем пользователя для приложения
sudo useradd -r -s /bin/bash -d /opt/vpn-bot vpnbot
sudo mkdir -p /opt/vpn-bot
sudo chown vpnbot:vpnbot /opt/vpn-bot
```

### 3. Копирование файлов

На локальной машине:

```bash
rsync -avz --progress \
    -e "ssh -i ~/.ssh/id_ed25519" \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='*.db' \
    --exclude='vpn_configs/*' \
    ./ root@194.26.27.31:/opt/vpn-bot/
```

### 4. Установка зависимостей

На VPS:

```bash
cd /opt/vpn-bot
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

### 5. Настройка .env файла

На VPS:

```bash
nano /opt/vpn-bot/.env
```

Убедитесь, что все переменные правильно настроены.

### 6. Установка systemd сервисов

Копируем файлы сервисов:

```bash
# На VPS
sudo cp deploy/systemd/vpn-bot.service /etc/systemd/system/
sudo cp deploy/systemd/vpn-yoomoney.service /etc/systemd/system/

# Обновляем пути в файлах (если нужно)
sudo sed -i 's|/opt/vpn-bot|/opt/vpn-bot|g' /etc/systemd/system/vpn-bot.service
sudo sed -i 's|vpnbot|root|g' /etc/systemd/system/vpn-bot.service
sudo sed -i 's|/opt/vpn-bot|/opt/vpn-bot|g' /etc/systemd/system/vpn-yoomoney.service
sudo sed -i 's|vpnbot|root|g' /etc/systemd/system/vpn-yoomoney.service

# Активируем и запускаем сервисы
sudo systemctl daemon-reload
sudo systemctl enable vpn-bot.service
sudo systemctl enable vpn-yoomoney.service
sudo systemctl start vpn-bot.service
sudo systemctl start vpn-yoomoney.service
```

### 7. Проверка статуса

```bash
sudo systemctl status vpn-bot.service
sudo systemctl status vpn-yoomoney.service
```

### 8. Настройка Nginx (опционально)

Если используете nginx как reverse proxy:

```bash
# Копируем конфигурацию
sudo cp deploy/nginx/vpn-bot.conf /etc/nginx/sites-available/vpn-bot.conf
sudo ln -s /etc/nginx/sites-available/vpn-bot.conf /etc/nginx/sites-enabled/

# Проверяем конфигурацию
sudo nginx -t

# Перезагружаем nginx
sudo systemctl reload nginx
```

### 9. Настройка SSL (Let's Encrypt)

Для HTTPS (рекомендуется):

```bash
sudo apt-get update
sudo apt-get install certbot python3-certbot-nginx

# Получаем сертификат
sudo certbot --nginx -d moroz.myftp.biz

# Автоматическое обновление
sudo certbot renew --dry-run
```

После установки SSL раскомментируйте HTTPS секцию в nginx конфигурации.

## 🔧 Управление сервисами

### Просмотр статуса

```bash
sudo systemctl status vpn-bot.service
sudo systemctl status vpn-yoomoney.service
```

### Просмотр логов

```bash
# Логи бота
sudo journalctl -u vpn-bot.service -f

# Логи YooMoney сервера
sudo journalctl -u vpn-yoomoney.service -f

# Последние 100 строк
sudo journalctl -u vpn-bot.service -n 100

# Логи за сегодня
sudo journalctl -u vpn-bot.service --since today
```

### Перезапуск сервисов

```bash
sudo systemctl restart vpn-bot.service
sudo systemctl restart vpn-yoomoney.service
```

### Остановка сервисов

```bash
sudo systemctl stop vpn-bot.service
sudo systemctl stop vpn-yoomoney.service
```

### Отключение автозапуска

```bash
sudo systemctl disable vpn-bot.service
sudo systemctl disable vpn-yoomoney.service
```

## 🔄 Обновление приложения

### Автоматическое обновление

Просто запустите скрипт развертывания еще раз:

```bash
./deploy/deploy.sh
```

Он обновит файлы и перезапустит сервисы.

### Ручное обновление

```bash
# 1. Остановите сервисы
sudo systemctl stop vpn-bot.service vpn-yoomoney.service

# 2. Сделайте бэкап базы данных
ssh root@194.26.27.31 "cp /opt/vpn-bot/database.db /opt/vpn-bot/database.db.backup"

# 3. Скопируйте новые файлы (см. раздел "Копирование файлов")

# 4. Обновите зависимости
ssh root@194.26.27.31 "cd /opt/vpn-bot && python3 -m pip install -r requirements.txt"

# 5. Запустите миграции базы данных (если нужно)
ssh root@194.26.27.31 "cd /opt/vpn-bot && python3 -c 'from database import init_db; init_db()'"

# 6. Запустите сервисы
sudo systemctl start vpn-bot.service vpn-yoomoney.service
```

## 🛠️ Устранение неполадок

### Сервис не запускается

1. Проверьте логи:
```bash
sudo journalctl -u vpn-bot.service -n 50
```

2. Проверьте файл .env:
```bash
cat /opt/vpn-bot/.env
```

3. Проверьте права доступа:
```bash
ls -la /opt/vpn-bot/
```

### Бот не отвечает

1. Проверьте статус сервиса
2. Проверьте логи на ошибки
3. Проверьте BOT_TOKEN в .env
4. Проверьте интернет-соединение

### YooMoney webhook не работает

1. Проверьте, что сервер доступен:
```bash
curl http://moroz.myftp.biz:8888/health
```

2. Проверьте логи YooMoney сервера:
```bash
sudo journalctl -u vpn-yoomoney.service -f
```

3. Проверьте настройки YooMoney:
   - Redirect URI должен быть: `http://moroz.myftp.biz:8888/yoomoney_redirect`
   - Notification URI должен быть: `http://moroz.myftp.biz:8888/yoomoney_webhook`

4. Проверьте firewall:
```bash
sudo ufw status
sudo ufw allow 8888/tcp
```

### Проблемы с базой данных

1. Проверьте права доступа к файлу БД:
```bash
ls -la /opt/vpn-bot/database.db
```

2. Переинициализируйте БД:
```bash
cd /opt/vpn-bot
python3 -c 'from database import init_db; init_db()'
```

3. Проверьте SQLite:
```bash
sqlite3 /opt/vpn-bot/database.db ".tables"
```

## 📊 Мониторинг

### Проверка использования ресурсов

```bash
# Использование CPU и памяти
top -p $(pgrep -f "python3.*bot.py")
top -p $(pgrep -f "python3.*start_yoomoney_server.py")

# Или через systemd
systemctl status vpn-bot.service
systemctl status vpn-yoomoney.service
```

### Проверка подключений

```bash
# Активные подключения
netstat -tulpn | grep 8888

# Логи nginx
tail -f /var/log/nginx/vpn-bot-access.log
```

## 🔒 Безопасность

1. **Используйте отдельного пользователя** вместо root для запуска сервисов
2. **Ограничьте права доступа** к файлам приложения
3. **Настройте firewall** (откройте только необходимые порты)
4. **Используйте HTTPS** для YooMoney (Let's Encrypt)
5. **Регулярно обновляйте** зависимости
6. **Делайте бэкапы** базы данных

### Пример настройки firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 8888/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## 📞 Поддержка

Если возникли проблемы:
1. Проверьте логи сервисов
2. Проверьте настройки в .env
3. Убедитесь, что все зависимости установлены
4. Проверьте сетевое подключение и firewall

