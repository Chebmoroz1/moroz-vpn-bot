# 🚀 Быстрое развертывание на VPS

## Предварительные требования

- ✅ VPS сервер (Ubuntu/Debian) с SSH доступом
- ✅ Домен, указывающий на VPS (для YooMoney)
- ✅ SSH ключ для доступа к серверу
- ✅ Telegram Bot Token
- ✅ YooMoney учетные данные

## Шаг 1: Настройка переменных окружения

```bash
cd /path/to/vpn-bot
cp .env.example .env
nano .env
```

Заполните обязательные параметры:

```env
# Telegram Bot
BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_id

# Server
SERVER_HOST=194.26.27.31
SERVER_USER=root
SERVER_SSH_KEY=~/.ssh/id_ed25519

# Web Server
WEB_SERVER_DOMAIN=moroz.myftp.biz
WEB_SERVER_PORT=8888

# YooMoney
YMONEY_CLIENT_ID=your_yoomoney_client_id
YMONEY_CLIENT_SECRET=your_yoomoney_client_secret
YMONEY_WALLET=your_yoomoney_wallet
```

## Шаг 2: Запуск автоматического развертывания

```bash
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

Скрипт автоматически:
- ✅ Скопирует файлы на VPS
- ✅ Установит зависимости Python
- ✅ Настроит systemd сервисы
- ✅ Инициализирует базу данных
- ✅ Запустит бота и YooMoney сервер

## Шаг 3: Проверка работы

### Проверка статуса сервисов

```bash
ssh root@194.26.27.31 'sudo systemctl status vpn-bot.service vpn-yoomoney.service'
```

### Просмотр логов

```bash
# Логи бота
ssh root@194.26.27.31 'sudo journalctl -u vpn-bot.service -f'

# Логи YooMoney
ssh root@194.26.27.31 'sudo journalctl -u vpn-yoomoney.service -f'
```

### Проверка YooMoney сервера

```bash
curl http://moroz.myftp.biz:8888/health
```

Должен вернуть: `{"status":"ok","service":"yoomoney_backend"}`

## Шаг 4: Настройка YooMoney (если еще не сделано)

1. Откройте [YooMoney API](https://yoomoney.ru/docs/payment-buttons/using-api/forms)
2. В настройках приложения укажите:
   - **Redirect URI**: `http://moroz.myftp.biz:8888/yoomoney_redirect`
   - **Notification URI**: `http://moroz.myftp.biz:8888/yoomoney_webhook`
   - **Site URL**: `http://moroz.myftp.biz`

## Шаг 5: Тестирование

1. Откройте Telegram бота
2. Отправьте команду `/start`
3. Попробуйте создать VPN ключ
4. Попробуйте оплатить VPN через YooMoney

## 🔧 Управление сервисами

### Перезапуск

```bash
ssh root@194.26.27.31 'sudo systemctl restart vpn-bot.service vpn-yoomoney.service'
```

### Остановка

```bash
ssh root@194.26.27.31 'sudo systemctl stop vpn-bot.service vpn-yoomoney.service'
```

### Просмотр логов

```bash
# Бот
ssh root@194.26.27.31 'sudo journalctl -u vpn-bot.service -n 100'

# YooMoney
ssh root@194.26.27.31 'sudo journalctl -u vpn-yoomoney.service -n 100'
```

## 🔄 Обновление

Для обновления приложения просто запустите скрипт развертывания еще раз:

```bash
./deploy/deploy.sh
```

## ❌ Устранение проблем

### Бот не отвечает

1. Проверьте статус: `sudo systemctl status vpn-bot.service`
2. Проверьте логи: `sudo journalctl -u vpn-bot.service -n 50`
3. Проверьте BOT_TOKEN в .env файле

### YooMoney не работает

1. Проверьте, что сервер доступен: `curl http://moroz.myftp.biz:8888/health`
2. Проверьте firewall: `sudo ufw status`
3. Проверьте логи: `sudo journalctl -u vpn-yoomoney.service -f`
4. Убедитесь, что в YooMoney правильно указаны URI

### Проблемы с базой данных

```bash
ssh root@194.26.27.31
cd /opt/vpn-bot
python3 -c 'from database import init_db; init_db()'
```

## 📚 Дополнительная документация

- [DEPLOYMENT.md](DEPLOYMENT.md) - Полная документация по развертыванию
- [deploy/README.md](deploy/README.md) - Документация по скриптам развертывания
- [YOOMONEY_SETUP.md](YOOMONEY_SETUP.md) - Настройка YooMoney

## 🔐 Безопасность

После развертывания рекомендуется:

1. ✅ Настроить firewall
2. ✅ Использовать HTTPS (Let's Encrypt)
3. ✅ Создать отдельного пользователя для приложения
4. ✅ Ограничить права доступа к файлам

Подробнее см. в [DEPLOYMENT.md](DEPLOYMENT.md#безопасность).

