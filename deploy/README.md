# Скрипты развертывания VPN Bot

Эта папка содержит скрипты и конфигурации для развертывания VPN Bot на VPS сервере.

## 📁 Структура

```
deploy/
├── deploy.sh              # Главный скрипт развертывания
├── systemd/               # Systemd сервисы
│   ├── vpn-bot.service    # Сервис для Telegram бота
│   └── vpn-yoomoney.service # Сервис для YooMoney веб-сервера
└── nginx/                 # Nginx конфигурации
    └── vpn-bot.conf       # Конфигурация reverse proxy
```

## 🚀 Быстрый старт

### Автоматическое развертывание

```bash
cd /path/to/vpn-bot
./deploy/deploy.sh
```

### Ручная настройка

1. Скопируйте файлы на VPS
2. Установите зависимости
3. Настройте .env файл
4. Установите systemd сервисы
5. Запустите сервисы

Подробные инструкции см. в [DEPLOYMENT.md](../DEPLOYMENT.md).

## ⚙️ Настройка переменных окружения

Перед запуском убедитесь, что файл `.env` настроен правильно:

```bash
cp .env.example .env
nano .env
```

Обязательные параметры:
- `BOT_TOKEN` - токен Telegram бота
- `ADMIN_ID` - ваш Telegram ID
- `SERVER_HOST` - IP адрес VPS сервера
- `WEB_SERVER_DOMAIN` - домен для YooMoney
- `YMONEY_CLIENT_ID` - ID YooMoney приложения
- `YMONEY_CLIENT_SECRET` - секретный ключ YooMoney
- `YMONEY_WALLET` - номер кошелька YooMoney

## 🔧 Systemd сервисы

### VPN Bot Service

Автоматически запускает Telegram бота при загрузке системы.

```bash
# Запуск
sudo systemctl start vpn-bot.service

# Остановка
sudo systemctl stop vpn-bot.service

# Перезапуск
sudo systemctl restart vpn-bot.service

# Статус
sudo systemctl status vpn-bot.service

# Логи
sudo journalctl -u vpn-bot.service -f
```

### YooMoney Service

Автоматически запускает веб-сервер для обработки платежей.

```bash
# Запуск
sudo systemctl start vpn-yoomoney.service

# Остановка
sudo systemctl stop vpn-yoomoney.service

# Перезапуск
sudo systemctl restart vpn-yoomoney.service

# Статус
sudo systemctl status vpn-yoomoney.service

# Логи
sudo journalctl -u vpn-yoomoney.service -f
```

## 🌐 Nginx конфигурация

Nginx используется как reverse proxy для YooMoney веб-сервера.

### Установка

```bash
# Копируем конфигурацию
sudo cp deploy/nginx/vpn-bot.conf /etc/nginx/sites-available/vpn-bot.conf

# Активируем
sudo ln -s /etc/nginx/sites-available/vpn-bot.conf /etc/nginx/sites-enabled/

# Проверяем конфигурацию
sudo nginx -t

# Перезагружаем nginx
sudo systemctl reload nginx
```

### HTTPS (Let's Encrypt)

После установки SSL сертификата раскомментируйте HTTPS секцию в конфигурации:

```bash
sudo nano /etc/nginx/sites-available/vpn-bot.conf
```

## 📝 Полезные команды

### Проверка статуса всех сервисов

```bash
sudo systemctl status vpn-bot.service vpn-yoomoney.service
```

### Просмотр логов

```bash
# Логи бота
sudo journalctl -u vpn-bot.service -f

# Логи YooMoney
sudo journalctl -u vpn-yoomoney.service -f

# Последние 100 строк
sudo journalctl -u vpn-bot.service -n 100
```

### Перезапуск всех сервисов

```bash
sudo systemctl restart vpn-bot.service vpn-yoomoney.service
```

### Проверка портов

```bash
# Проверка порта 8888 (YooMoney сервер)
netstat -tulpn | grep 8888

# Проверка открытых портов
sudo ss -tulpn
```

## 🔄 Обновление

Для обновления приложения просто запустите скрипт развертывания еще раз:

```bash
./deploy/deploy.sh
```

Скрипт автоматически:
- Обновит файлы на VPS
- Установит новые зависимости
- Перезапустит сервисы

## 🛠️ Устранение неполадок

### Сервис не запускается

1. Проверьте логи: `sudo journalctl -u vpn-bot.service -n 50`
2. Проверьте .env файл: `cat /opt/vpn-bot/.env`
3. Проверьте права доступа: `ls -la /opt/vpn-bot/`

### Проблемы с подключением

1. Проверьте firewall: `sudo ufw status`
2. Проверьте порты: `netstat -tulpn | grep 8888`
3. Проверьте сетевые настройки

### Проблемы с базой данных

1. Проверьте права: `ls -la /opt/vpn-bot/database.db`
2. Переинициализируйте: `cd /opt/vpn-bot && python3 -c 'from database import init_db; init_db()'`

## 📚 Дополнительная документация

- [DEPLOYMENT.md](../DEPLOYMENT.md) - Полная документация по развертыванию
- [README.md](../README.md) - Общая информация о проекте
- [TECHNICAL_SPECIFICATION.md](../TECHNICAL_SPECIFICATION.md) - Техническая спецификация

