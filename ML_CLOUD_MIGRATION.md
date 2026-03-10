# Миграция с YooMoney на ML Cloud

## ✅ Что уже сделано:

1. ✅ Создан `ml_cloud_backend.py` - Flask endpoints для ML Cloud
2. ✅ Создан `start_ml_cloud_server.py` - скрипт запуска сервера
3. ✅ Создан systemd сервис `vpn-ml-cloud.service`
4. ✅ Обновлен `bot.py` - меню доната (минимум 250₽, комиссия 2%)
5. ✅ Добавлены переменные окружения в `.env`

## 🔄 План переключения:

### Вариант 1: Полная замена (рекомендуется)

```bash
# 1. Остановить старый сервис
systemctl stop vpn-yoomoney.service

# 2. Запустить новый сервис
systemctl start vpn-ml-cloud.service
systemctl enable vpn-ml-cloud.service

# 3. Проверить статус
systemctl status vpn-ml-cloud.service

# 4. Проверить логи
journalctl -u vpn-ml-cloud.service -f

# 5. Проверить что сервер отвечает
curl http://localhost:8888/health

# 6. Отключить автозапуск старого сервиса (опционально)
systemctl disable vpn-yoomoney.service
```

## 📋 Проверка работы:

### 1. Проверка здоровья сервиса:
```bash
curl http://localhost:8888/health
# Ожидается: {"status":"ok","service":"ml_cloud_backend"}
```

### 2. Тест генерации платежной ссылки:
```bash
curl -X POST http://localhost:8888/generate_payment_uri \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "amount": 250,
    "description": "Тестовый платеж",
    "payment_type": "donation"
  }'
```

### 3. Проверка логов:
```bash
journalctl -u vpn-ml-cloud.service -n 50
```

## 🔧 Откат (если нужно вернуться к YooMoney):

```bash
# 1. Остановить ML Cloud
systemctl stop vpn-ml-cloud.service
systemctl disable vpn-ml-cloud.service

# 2. Запустить YooMoney
systemctl start vpn-yoomoney.service
systemctl enable vpn-yoomoney.service

# 3. Проверить
systemctl status vpn-yoomoney.service
```

## 📝 Примечания:

- Оба сервиса используют один и тот же порт (8888) по умолчанию
- Переменные окружения загружаются из `/opt/vpn-bot/.env`
- Логи доступны через `journalctl -u vpn-ml-cloud.service`
- Минимальная сумма платежа: 250₽
- Комиссия: 2% (включается автоматически)

## 🆘 Устранение проблем:

### Ошибка: "ML_CLOUD_EMAIL не найдено"
```bash
# Проверить переменные окружения
grep ML_CLOUD /opt/vpn-bot/.env

# Если отсутствуют - добавить:
echo "ML_CLOUD_EMAIL=chebmoroz@gmail.com" >> /opt/vpn-bot/.env
echo "ML_CLOUD_PASSWORD=bewzes-quzpuk-2nuntU" >> /opt/vpn-bot/.env
```

### Ошибка: "Порт уже занят"
```bash
# Проверить кто использует порт
lsof -i :8888
netstat -tulpn | grep 8888
```

### Проблемы с токеном
```bash
# Удалить старый токен и пересоздать
rm /tmp/ml_cloud_token.json
systemctl restart vpn-ml-cloud.service
```

