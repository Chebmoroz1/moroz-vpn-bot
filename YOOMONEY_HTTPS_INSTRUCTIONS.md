# Настройка HTTPS для YooMoney

## ⚠️ Важно!

**YooMoney требует HTTPS для всех URL (Redirect URI и Notification URI).** HTTP не принимается.

## Проблема

YooMoney отклоняет ссылки `http://moroz.myftp.biz:8888/...` потому что:
1. Требуется HTTPS вместо HTTP
2. Порт 8888 может быть заблокирован firewall
3. YooMoney проверяет доступность URL извне

## Решение

### Вариант 1: Использовать Nginx с HTTPS на порту 443 (Рекомендуется)

1. **Получите SSL сертификат** через Let's Encrypt (certbot имеет проблемы, но можно исправить):
   ```bash
   # На VPS
   apt-get update
   apt-get install -y snapd
   snap install --classic certbot
   ln -sf /snap/bin/certbot /usr/bin/certbot
   
   # Остановите nginx и YooMoney сервер временно
   systemctl stop nginx
   systemctl stop vpn-yoomoney.service
   
   # Получите сертификат
   certbot certonly --standalone -d moroz.myftp.biz --email chebmoroz@gmail.com
   
   # Запустите сервисы обратно
   systemctl start nginx
   systemctl start vpn-yoomoney.service
   ```

2. **Настройте nginx для HTTPS**:
   - Используйте порт 443 с SSL
   - Настройте редирект с HTTP на HTTPS

3. **Обновите URL в YooMoney**:
   - Redirect URI: `https://moroz.myftp.biz/yoomoney_redirect`
   - Notification URI: `https://moroz.myftp.biz/yoomoney_webhook`
   - Site URL: `https://moroz.myftp.biz`

### Вариант 2: Использовать Cloudflare (Проще и быстрее)

1. Добавьте домен `moroz.myftp.biz` в Cloudflare
2. Настройте DNS записи (A запись на IP сервера)
3. Включите SSL/TLS в Cloudflare (Full или Full (strict))
4. Cloudflare автоматически предоставит HTTPS
5. Обновите URL в YooMoney на `https://moroz.myftp.biz/...`

### Вариант 3: Использовать другой домен с уже настроенным HTTPS

Если у вас есть другой домен с HTTPS, используйте его для YooMoney.

## Текущая ситуация

- ✅ Nginx установлен и работает на порту 80
- ✅ YooMoney сервер работает на порту 8888
- ✅ Nginx настроен как reverse proxy
- ❌ SSL сертификат не получен (проблемы с certbot)

## Рекомендация

Используйте Cloudflare для быстрой настройки HTTPS - это самый простой способ.

После настройки HTTPS обновите:
1. `.env` файл: измените `http://` на `https://`
2. URL в настройках YooMoney приложения
3. Перезапустите YooMoney сервер: `systemctl restart vpn-yoomoney.service`

