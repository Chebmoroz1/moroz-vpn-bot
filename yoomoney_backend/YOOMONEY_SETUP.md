# Настройка приложения в ЮMoney

## URL для регистрации приложения

### Вариант 1: Использование IP адреса (если нет домена)

**Адрес сайта:**
```
http://194.26.27.31:5000
```

**Redirect URI:**
```
http://194.26.27.31:5000/yoomoney_redirect
```

**Notification URI:**
```
http://194.26.27.31:5000/yoomoney_webhook
```

### Вариант 2: Использование домена (если есть)

Если у вас есть домен, например `vpn.example.com`:

**Адрес сайта:**
```
https://vpn.example.com
```

**Redirect URI:**
```
https://vpn.example.com/yoomoney_redirect
```

**Notification URI:**
```
https://vpn.example.com/yoomoney_webhook
```

## Важные моменты:

1. **Redirect URI** должен точно совпадать с тем, что указано в `.env` файле (`YMONEY_REDIRECT_URI`)
2. **Notification URI** - это адрес, куда ЮMoney будет отправлять webhook-уведомления о платежах
3. Если используете HTTPS, убедитесь, что SSL сертификат настроен
4. Если используете HTTP, убедитесь, что порт 5000 открыт в firewall

## После регистрации:

1. Получите `CLIENT_ID` и `CLIENT_SECRET` от ЮMoney
2. Обновите файл `.env` на сервере:
   ```bash
   ssh root@194.26.27.31
   cd /root/yoomoney_backend
   nano .env
   ```
3. Заполните:
   ```
   YMONEY_CLIENT_ID=ваш_client_id
   YMONEY_CLIENT_SECRET=ваш_client_secret
   YMONEY_REDIRECT_URI=http://194.26.27.31:5000/yoomoney_redirect
   ```
4. Перезапустите бэкенд:
   ```bash
   systemctl restart yoomoney-backend
   ```

## Проверка доступности эндпоинтов:

```bash
# Проверка health check
curl http://194.26.27.31:5000/health

# Проверка redirect URI (должен вернуть ошибку без кода, но это нормально)
curl http://194.26.27.31:5000/yoomoney_redirect

# Проверка webhook (должен вернуть ошибку без данных, но это нормально)
curl -X POST http://194.26.27.31:5000/yoomoney_webhook
```

