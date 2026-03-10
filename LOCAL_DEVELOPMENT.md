# Локальная разработка YooMoney сервера

## ⚠️ Важно

**YooMoney НЕ будет работать, если запустить сервер локально без дополнительной настройки**, потому что:
- YooMoney отправляет webhook'и на домен VPS (`moroz.myftp.biz:8888`)
- Локальный сервер недоступен из интернета
- Домен `moroz.myftp.biz` указывает на VPS, а не на вашу локальную машину

## ✅ Варианты решения

### 1. Запуск на VPS (Рекомендуется для продакшена)

**Самый правильный вариант** - запускать сервер на VPS постоянно:

```bash
# На VPS сервере
cd /path/to/vpn-bot
python3 start_yoomoney_server.py
```

Или через systemd/PM2 для автозапуска.

### 2. SSH туннель (Для тестирования)

Можно использовать SSH туннель, чтобы перенаправлять запросы с VPS на локальную машину:

#### Настройка SSH туннеля:

```bash
# 1. Настройте туннель
./ssh_tunnel_setup.sh

# 2. На VPS должен быть запущен reverse proxy или перенаправление
# Или используйте SSH reverse tunnel:
ssh -R 8888:localhost:8888 -i ~/.ssh/id_ed25519 root@194.26.27.31
```

#### Проблема с reverse tunnel:
SSH reverse tunnel работает только для входящих соединений на VPS, но не поможет с доменом. Нужен другой подход.

### 3. Ngrok (Для быстрого тестирования)

Ngrok создает публичный туннель к локальному серверу:

```bash
# 1. Установите ngrok
# macOS: brew install ngrok
# Linux: скачайте с https://ngrok.com/

# 2. Запустите ngrok туннель
ngrok http 8888

# 3. Ngrok даст вам публичный URL, например: https://abc123.ngrok.io
# 4. Временно измените в .env:
#    WEB_SERVER_DOMAIN=abc123.ngrok.io
#    YMONEY_REDIRECT_URI=https://abc123.ngrok.io/yoomoney_redirect
#    YMONEY_NOTIFICATION_URI=https://abc123.ngrok.io/yoomoney_webhook

# 5. Обновите настройки в YooMoney (Redirect URI и Notification URI)
```

**⚠️ Внимание:** 
- Ngrok URL меняется при каждом перезапуске (бесплатный план)
- Нужно обновлять настройки в YooMoney каждый раз
- Подходит только для тестирования

### 4. Nginx reverse proxy на VPS

Настройте nginx на VPS для перенаправления запросов на ваш локальный сервер через SSH туннель:

**На VPS:**
```nginx
# /etc/nginx/sites-available/yoomoney
server {
    listen 8888;
    server_name moroz.myftp.biz;

    location / {
        proxy_pass http://127.0.0.1:8889;  # Локальный порт на VPS
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**На локальной машине:**
```bash
# Создайте SSH туннель (прямой, не reverse)
ssh -L 8889:localhost:8888 -i ~/.ssh/id_ed25519 -N root@194.26.27.31

# Запустите локальный сервер
python start_yoomoney_server.py
```

Это работает так:
1. YooMoney → moroz.myftp.biz:8888 (VPS)
2. Nginx на VPS → localhost:8889 (VPS)
3. SSH туннель → localhost:8888 (ваша локальная машина)

## 🔧 Текущая конфигурация

В `config.py` указано:
- `WEB_SERVER_DOMAIN = "moroz.myftp.biz"`
- `WEB_SERVER_PORT = 8888`
- `YMONEY_REDIRECT_URI = "http://moroz.myftp.biz:8888/yoomoney_redirect"`
- `YMONEY_NOTIFICATION_URI = "http://moroz.myftp.biz:8888/yoomoney_webhook"`

Эти URL должны быть доступны из интернета для работы YooMoney.

## 📝 Рекомендация

**Для разработки:**
- Используйте ngrok для быстрого тестирования
- Или настройте nginx reverse proxy на VPS

**Для продакшена:**
- Запускайте сервер на VPS через systemd/PM2/supervisor
- Используйте nginx как reverse proxy с SSL (Let's Encrypt)
- Настройте домен с HTTPS

## 🚀 Запуск для тестирования

Если нужно протестировать локально с ngrok:

```bash
# 1. Запустите ngrok
ngrok http 8888

# 2. Получите ngrok URL (например: https://abc123.ngrok.io)

# 3. Временно измените .env файл:
#    export WEB_SERVER_DOMAIN="abc123.ngrok.io"
#    export YMONEY_REDIRECT_URI="https://abc123.ngrok.io/yoomoney_redirect"
#    export YMONEY_NOTIFICATION_URI="https://abc123.ngrok.io/yoomoney_webhook"

# 4. Обновите настройки в YooMoney приложении

# 5. Запустите локальный сервер
python start_yoomoney_server.py
```

