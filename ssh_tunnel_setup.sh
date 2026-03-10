#!/bin/bash
# Скрипт для настройки SSH туннеля для локальной разработки
# Это позволит запускать YooMoney сервер локально, но получать запросы через VPS

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Настройка SSH туннеля для YooMoney сервера ===${NC}"
echo ""

# Проверяем, не запущен ли уже туннель
if lsof -Pi :8888 -sTCP:LISTEN -t >/dev/null ; then
    echo -e "${RED}⚠️  Порт 8888 уже занят!${NC}"
    echo "Возможно, туннель уже запущен или сервер работает локально."
    read -p "Продолжить? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Параметры из config.py (можно изменить)
VPS_HOST="194.26.27.31"
VPS_USER="root"
LOCAL_PORT=8888
REMOTE_PORT=8888
SSH_KEY="$HOME/.ssh/id_ed25519"

echo -e "${GREEN}Параметры туннеля:${NC}"
echo "  VPS сервер: ${VPS_USER}@${VPS_HOST}"
echo "  Локальный порт: ${LOCAL_PORT}"
echo "  Удаленный порт: ${REMOTE_PORT}"
echo ""

# Проверяем наличие SSH ключа
if [ ! -f "$SSH_KEY" ]; then
    echo -e "${RED}❌ SSH ключ не найден: ${SSH_KEY}${NC}"
    echo "Проверьте путь к ключу в config.py или создайте новый ключ."
    exit 1
fi

echo -e "${YELLOW}Создание SSH туннеля...${NC}"
echo ""

# Команда для создания туннеля
SSH_CMD="ssh -N -f -L ${LOCAL_PORT}:localhost:${REMOTE_PORT} -i ${SSH_KEY} ${VPS_USER}@${VPS_HOST}"

# Проверяем, существует ли туннель
if pgrep -f "ssh.*-L ${LOCAL_PORT}:localhost:${REMOTE_PORT}" > /dev/null; then
    echo -e "${GREEN}✅ Туннель уже запущен${NC}"
else
    # Создаем туннель
    if eval "$SSH_CMD"; then
        echo -e "${GREEN}✅ SSH туннель успешно создан!${NC}"
        echo ""
        echo -e "${YELLOW}Важно:${NC}"
        echo "1. На VPS должен быть запущен YooMoney сервер на порту ${REMOTE_PORT}"
        echo "2. Или запустите сервер локально (он будет доступен через туннель)"
        echo "3. YooMoney будет отправлять webhook'и на moroz.myftp.biz:8888"
        echo "4. Эти запросы будут перенаправлены на ваш локальный сервер"
        echo ""
        echo -e "${GREEN}Для остановки туннеля выполните:${NC}"
        echo "  pkill -f 'ssh.*-L ${LOCAL_PORT}:localhost:${REMOTE_PORT}'"
    else
        echo -e "${RED}❌ Ошибка при создании туннеля${NC}"
        exit 1
    fi
fi

echo ""
echo -e "${GREEN}=== Туннель активен ===${NC}"

