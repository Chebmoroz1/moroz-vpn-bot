# Инструкция по запуску бота

## Важно!

⚠️ **Запускайте бота только в одном месте!** Если бот уже запущен в другом терминале или на сервере, вы получите ошибку конфликта.

## Перед запуском

1. **Остановите старые процессы бота:**
   ```bash
   ps aux | grep bot.py | grep -v grep
   kill -9 <PID>  # если найден процесс
   ```

2. **Проверьте подключение к серверу:**
   ```bash
   python test_connection.py
   ```

## Запуск бота

### Локальная разработка (macOS)

```bash
cd /Users/chebmoroz/vpn-bot
python bot.py
```

### Запуск в фоновом режиме (macOS)

```bash
cd /Users/chebmoroz/vpn-bot
nohup python bot.py > bot.log 2>&1 &
```

### Остановка фонового процесса

```bash
ps aux | grep bot.py | grep -v grep
kill <PID>
```

## Проверка работы

1. Откройте бота в Telegram: `@Moroz_VpnBot`
2. Отправьте `/start`
3. Попробуйте создать VPN ключ

## Логи

Если бот запущен в фоновом режиме, логи сохраняются в `bot.log`:

```bash
tail -f bot.log
```

## Проблемы

### Ошибка "Conflict: terminated by other getUpdates request"

**Причина:** Бот уже запущен в другом процессе.

**Решение:**
1. Найдите все процессы бота: `ps aux | grep bot.py`
2. Остановите их: `kill -9 <PID>`
3. Подождите 5 секунд
4. Запустите бот снова

### Ошибка "ModuleNotFoundError: No module named 'paramiko'"

**Причина:** Зависимости не установлены или используется другое окружение Python.

**Решение:**
```bash
cd /Users/chebmoroz/vpn-bot
python -m pip install -r requirements.txt
```

### Ошибка при генерации ключа

**Проверьте:**
1. SSH подключение к серверу: `ssh root@194.26.27.31`
2. Работает ли Docker контейнер: `python test_connection.py`
3. Логи бота для детальной информации

