# Инструкция по настройке YooMoney

## Важные замечания

⚠️ **YooMoney не работает с IP-адресами!** Обязательно используйте домен `moroz.myftp.biz`.

## Шаг 1: Регистрация приложения в YooMoney

1. **Войдите в YooMoney:**
   - Зайдите на https://yoomoney.ru
   - Войдите в свой кошелек (если нет - зарегистрируйтесь)

2. **Перейдите на страницу регистрации приложения:**
   - Ссылка: https://yoomoney.ru/myservices/new
   - Или через меню: **"Для бизнеса"** → **"Подключить прием платежей"** → **"Создать приложение"**

3. **Заполните форму регистрации:**
   - **Название для пользователей**: `Moroz_vpn` (или любое другое)
   - **Адрес сайта**: `http://moroz.myftp.biz` (или `https://moroz.myftp.biz` после настройки HTTPS)
   - **Почта для связи**: ваш email (например, `chebmoroz@gmail.com`)
   - **Redirect URI**: `http://moroz.myftp.biz:8888/yoomoney_redirect`
   - **Notification URI**: `http://moroz.myftp.biz:8888/yoomoney_webhook`
   - **Логотип**: (опционально) загрузите логотип приложения
   - **✅ ВАЖНО!** Установите флажок: **"Проверять подлинность приложения (OAuth2 client_secret)"**

4. **Подтвердите регистрацию:**
   - Нажмите кнопку **"Подтвердить"**
   - После регистрации вы получите:

### Что вы получите после регистрации:

✅ **CLIENT_ID** (идентификатор клиента)
   - Пример: `ED3F92226A61D36D60400C8DF4E3E89064A597DA345FE9E286741685E5154B2E`
   - Этот ID вы уже получили и добавили в настройки

✅ **CLIENT_SECRET** (секретное слово)
   - ⚠️ **ВАЖНО:** Это показывается только один раз при создании приложения!
   - Если вы его не сохранили, нужно будет создать новое приложение или сбросить секрет
   - Выглядит как длинная строка символов (например, `ABC123XYZ...`)

5. **Сохраните CLIENT_SECRET:**
   - Скопируйте его сразу после создания приложения
   - Сохраните в безопасном месте
   - Добавьте в админ-панель бота или в `.env` файл

## Шаг 2: Настройка URI в приложении YooMoney

В настройках приложения YooMoney укажите следующие URI:

### Redirect URI (для OAuth 2.0)
```
http://moroz.myftp.biz:8888/yoomoney_redirect
```

### Notification URI (для webhook уведомлений)
```
http://moroz.myftp.biz:8888/yoomoney_webhook
```

### Адрес сайта
```
http://moroz.myftp.biz
```

## Шаг 3: Настройка переменных окружения

Откройте файл `.env` и заполните:

```env
# YooMoney
YMONEY_CLIENT_ID=ваш_client_id_здесь
YMONEY_CLIENT_SECRET=ваш_client_secret_здесь
YMONEY_WALLET=номер_вашего_кошелька
```

**Где взять номер кошелька:**
- Номер кошелька YooMoney (например, `410011234567890`)
- Его можно найти в личном кабинете YooMoney

## Шаг 4: Настройка домена

Убедитесь, что домен `moroz.myftp.biz` указывает на IP адрес сервера `194.26.27.31`:

```bash
# Проверить DNS запись
nslookup moroz.myftp.biz

# Должен вернуть:
# moroz.myftp.biz  ->  194.26.27.31
```

## Шаг 5: Настройка портов

Убедитесь, что порт `8888` открыт на сервере:

```bash
# На сервере проверить открыт ли порт
sudo netstat -tlnp | grep 8888

# Если нужно открыть порт (для ufw)
sudo ufw allow 8888/tcp
```

## Шаг 6: Запуск сервера

### Локально для тестирования:
```bash
python start_yoomoney_server.py
```

### На сервере (через systemd):
Создайте файл `/etc/systemd/system/yoomoney-backend.service`:

```ini
[Unit]
Description=YooMoney Backend Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/vpn-bot
ExecStart=/usr/bin/python3 /root/vpn-bot/start_yoomoney_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Затем:
```bash
sudo systemctl daemon-reload
sudo systemctl enable yoomoney-backend
sudo systemctl start yoomoney-backend
sudo systemctl status yoomoney-backend
```

## Шаг 7: Проверка работы

1. Проверьте, что сервер запущен:
   ```bash
   curl http://moroz.myftp.biz:8888/health
   ```

2. Проверьте, что YooMoney может достучаться до вашего сервера:
   - В настройках приложения YooMoney есть тест webhook
   - Или отправьте тестовый запрос:
     ```bash
     curl -X POST http://moroz.myftp.biz:8888/yoomoney_webhook \
       -d "notification_type=test&label=test123"
     ```

## Проблемы и решения

### Ошибка "Redirect URI mismatch"
- Убедитесь, что Redirect URI в `.env` точно совпадает с указанным в приложении YooMoney
- URI чувствительны к регистру и должны быть полными (с протоколом и портом)

### YooMoney не может достучаться до webhook
- Проверьте, что порт `8888` открыт на сервере
- Проверьте, что домен правильно указывает на сервер
- Проверьте firewall правила

### Платежи не обрабатываются
- Проверьте логи Flask сервера: `journalctl -u yoomoney-backend -f`
- Убедитесь, что Notification URI указан правильно в приложении YooMoney

## Структура URL

Все URL должны использовать домен `moroz.myftp.biz`:

- **OAuth Redirect**: `http://moroz.myftp.biz:8888/yoomoney_redirect`
- **Webhook**: `http://moroz.myftp.biz:8888/yoomoney_webhook`
- **Health Check**: `http://moroz.myftp.biz:8888/health`
- **Generate Payment**: `http://moroz.myftp.biz:8888/generate_payment_uri`

## Тестирование

После настройки можно протестировать:

1. Запустить бота
2. Нажать кнопку "💳 Оплатить VPN"
3. Перейти по платежной ссылке
4. Выполнить тестовый платеж
5. Проверить, что ключ создан автоматически

