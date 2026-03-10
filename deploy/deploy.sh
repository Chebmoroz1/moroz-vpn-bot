#!/bin/bash
# Скрипт развертывания VPN Bot на VPS сервере
# Использование: ./deploy/deploy.sh

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Переменные
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VPS_USER="${VPS_USER:-root}"
VPS_HOST="${VPS_HOST:-194.26.27.31}"
VPS_APP_DIR="${VPS_APP_DIR:-/opt/vpn-bot}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   VPN Bot - Развертывание на VPS${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Проверка наличия SSH ключа
if [ ! -f "$SSH_KEY" ]; then
    echo -e "${RED}❌ SSH ключ не найден: $SSH_KEY${NC}"
    echo "Создайте SSH ключ или укажите путь через переменную SSH_KEY"
    exit 1
fi

# Проверка SSH подключения
echo -e "${YELLOW}Проверка подключения к VPS...${NC}"
if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_HOST}" "echo 'OK'" &>/dev/null; then
    echo -e "${RED}❌ Не удалось подключиться к VPS серверу${NC}"
    echo "Проверьте:"
    echo "  - SSH ключ: $SSH_KEY"
    echo "  - Хост: ${VPS_USER}@${VPS_HOST}"
    echo "  - Сетевое подключение"
    exit 1
fi
echo -e "${GREEN}✅ Подключение к VPS установлено${NC}"
echo ""

# Сборка frontend (если Node.js установлен)
echo -e "${YELLOW}Сборка React frontend...${NC}"
if command -v npm &> /dev/null; then
    cd "$PROJECT_DIR/web_admin/frontend"
    if [ -d "node_modules" ]; then
        echo "  Установка зависимостей npm..."
        npm install --silent
        echo "  Сборка production версии..."
        npm run build
        echo -e "${GREEN}✅ Frontend собран${NC}"
    else
        echo "  Установка зависимостей npm..."
        npm install --silent
        echo "  Сборка production версии..."
        npm run build
        echo -e "${GREEN}✅ Frontend собран${NC}"
    fi
    cd "$PROJECT_DIR"
else
    echo -e "${YELLOW}⚠️  npm не найден, пропускаем сборку frontend${NC}"
    echo "  Frontend будет собран на сервере (если Node.js установлен)"
fi
echo ""

# Создание директорий на VPS
echo -e "${YELLOW}Создание директорий на VPS...${NC}"
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "mkdir -p $VPS_APP_DIR/{vpn_configs,logs}"
echo -e "${GREEN}✅ Директории созданы${NC}"
echo ""

# Копирование файлов
echo -e "${YELLOW}Копирование файлов на VPS...${NC}"
cd "$PROJECT_DIR"
tar --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='*.db' \
    --exclude='*.db-journal' \
    --exclude='vpn_configs' \
    --exclude='logs' \
    --exclude='.DS_Store' \
    --exclude='deploy' \
    --exclude='web_admin/frontend/node_modules' \
    -czf - . | ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "cd $VPS_APP_DIR && tar -xzf -"
echo -e "${GREEN}✅ Файлы скопированы${NC}"
echo ""

# Сборка frontend на сервере (если не был собран локально или для обновления)
echo -e "${YELLOW}Проверка и сборка frontend на сервере...${NC}"
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "bash -s" << ENDSSH
    VPS_APP_DIR="$VPS_APP_DIR"
    cd "\$VPS_APP_DIR/web_admin/frontend"
    
    if command -v npm &> /dev/null; then
        if [ ! -d "node_modules" ]; then
            echo "  Установка зависимостей npm на сервере..."
            npm install --silent
        fi
        echo "  Сборка production версии на сервере..."
        npm run build
        echo "✅ Frontend собран на сервере"
    else
        echo "⚠️  npm не найден на сервере, frontend не будет собран"
        echo "  Установите Node.js для сборки frontend: curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install -y nodejs"
    fi
ENDSSH
echo ""

# Установка зависимостей на VPS
echo -e "${YELLOW}Установка зависимостей Python...${NC}"
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "cd $VPS_APP_DIR && python3 -m pip install --upgrade pip && python3 -m pip install -r requirements.txt"
echo -e "${GREEN}✅ Зависимости установлены${NC}"
echo ""

# Копирование .env файла (если существует)
if [ -f "$PROJECT_DIR/.env" ]; then
    echo -e "${YELLOW}Копирование файла .env...${NC}"
    scp -i "$SSH_KEY" "$PROJECT_DIR/.env" "${VPS_USER}@${VPS_HOST}:${VPS_APP_DIR}/.env"
    echo -e "${GREEN}✅ Файл .env скопирован${NC}"
    echo ""
else
    echo -e "${YELLOW}⚠️  Файл .env не найден локально${NC}"
    echo "Создайте файл .env на VPS вручную или скопируйте .env.example"
    echo ""
fi

# Установка systemd сервисов
echo -e "${YELLOW}Установка systemd сервисов...${NC}"
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "bash -s" << 'ENDSSH'
    sudo systemctl stop vpn-bot.service 2>/dev/null || true
    sudo systemctl stop vpn-yoomoney.service 2>/dev/null || true
    sudo systemctl stop vpn-web-admin.service 2>/dev/null || true
ENDSSH

# Копирование systemd сервисов
scp -i "$SSH_KEY" "$SCRIPT_DIR/systemd/vpn-bot.service" "${VPS_USER}@${VPS_HOST}:/tmp/vpn-bot.service"
scp -i "$SSH_KEY" "$SCRIPT_DIR/systemd/vpn-yoomoney.service" "${VPS_USER}@${VPS_HOST}:/tmp/vpn-yoomoney.service"
scp -i "$SSH_KEY" "$SCRIPT_DIR/systemd/vpn-web-admin.service" "${VPS_USER}@${VPS_HOST}:/tmp/vpn-web-admin.service"

# Установка и активация сервисов
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "bash -s" << ENDSSH
    VPS_APP_DIR="$VPS_APP_DIR"
    VPS_USER="$VPS_USER"
    
    # Замена переменных в systemd файлах и исправление User/Group на root
    sudo sed "s|/opt/vpn-bot|$VPS_APP_DIR|g; s|User=.*|User=root|g; s|Group=.*|Group=root|g" /tmp/vpn-bot.service | sudo tee /etc/systemd/system/vpn-bot.service > /dev/null
    sudo sed "s|/opt/vpn-bot|$VPS_APP_DIR|g; s|User=.*|User=root|g; s|Group=.*|Group=root|g" /tmp/vpn-yoomoney.service | sudo tee /etc/systemd/system/vpn-yoomoney.service > /dev/null
    sudo sed "s|/opt/vpn-bot|$VPS_APP_DIR|g; s|User=.*|User=root|g; s|Group=.*|Group=root|g" /tmp/vpn-web-admin.service | sudo tee /etc/systemd/system/vpn-web-admin.service > /dev/null
    
    # Перезагрузка systemd и запуск сервисов
    sudo systemctl daemon-reload
    sudo systemctl enable vpn-bot.service
    sudo systemctl enable vpn-yoomoney.service
    sudo systemctl enable vpn-web-admin.service
ENDSSH

echo -e "${GREEN}✅ Systemd сервисы установлены${NC}"
echo ""

# Установка nginx конфигурации (если nginx установлен)
echo -e "${YELLOW}Проверка и установка nginx конфигурации...${NC}"
if ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "which nginx &>/dev/null"; then
    scp -i "$SSH_KEY" "$SCRIPT_DIR/nginx/vpn-bot.conf" "${VPS_USER}@${VPS_HOST}:/tmp/vpn-bot-nginx.conf"
    ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "bash -s" << 'ENDSSH'
        if [ -d "/etc/nginx/sites-available" ]; then
            sudo mv /tmp/vpn-bot-nginx.conf /etc/nginx/sites-available/vpn-bot.conf
            if [ ! -f "/etc/nginx/sites-enabled/vpn-bot.conf" ]; then
                sudo ln -s /etc/nginx/sites-available/vpn-bot.conf /etc/nginx/sites-enabled/vpn-bot.conf
            fi
            sudo nginx -t && sudo systemctl reload nginx
            echo "✅ Nginx конфигурация установлена"
        else
            echo "⚠️  Nginx sites-available не найден, пропускаем nginx конфигурацию"
        fi
ENDSSH
else
    echo -e "${YELLOW}⚠️  Nginx не установлен, пропускаем nginx конфигурацию${NC}"
fi
echo ""

# Инициализация базы данных
echo -e "${YELLOW}Инициализация базы данных...${NC}"
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "cd $VPS_APP_DIR && python3 -c 'from database import init_db; init_db()'"
echo -e "${GREEN}✅ База данных инициализирована${NC}"
echo ""

# Запуск сервисов
echo -e "${YELLOW}Запуск сервисов...${NC}"
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "bash -s" << 'ENDSSH'
    sudo systemctl start vpn-bot.service
    sudo systemctl start vpn-yoomoney.service
    sudo systemctl start vpn-web-admin.service
    
    sleep 3
    
    if sudo systemctl is-active --quiet vpn-bot.service; then
        echo "✅ VPN Bot сервис запущен"
    else
        echo "❌ VPN Bot сервис не запустился. Проверьте логи: sudo journalctl -u vpn-bot.service -f"
    fi
    
    if sudo systemctl is-active --quiet vpn-yoomoney.service; then
        echo "✅ YooMoney сервис запущен"
    else
        echo "❌ YooMoney сервис не запустился. Проверьте логи: sudo journalctl -u vpn-yoomoney.service -f"
    fi
    
    if sudo systemctl is-active --quiet vpn-web-admin.service; then
        echo "✅ Web Admin сервис запущен"
    else
        echo "❌ Web Admin сервис не запустился. Проверьте логи: sudo journalctl -u vpn-web-admin.service -f"
    fi
ENDSSH

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Развертывание завершено!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Полезные команды:${NC}"
echo "  Проверить статус сервисов:"
echo "    ssh ${VPS_USER}@${VPS_HOST} 'sudo systemctl status vpn-bot.service vpn-yoomoney.service vpn-web-admin.service'"
echo ""
echo "  Просмотр логов бота:"
echo "    ssh ${VPS_USER}@${VPS_HOST} 'sudo journalctl -u vpn-bot.service -f'"
echo ""
echo "  Просмотр логов YooMoney:"
echo "    ssh ${VPS_USER}@${VPS_HOST} 'sudo journalctl -u vpn-yoomoney.service -f'"
echo ""
echo "  Просмотр логов Web Admin:"
echo "    ssh ${VPS_USER}@${VPS_HOST} 'sudo journalctl -u vpn-web-admin.service -f'"
echo ""
echo "  Перезапуск сервисов:"
echo "    ssh ${VPS_USER}@${VPS_HOST} 'sudo systemctl restart vpn-bot.service vpn-yoomoney.service vpn-web-admin.service'"
echo ""
echo -e "${YELLOW}Примечание:${NC}"
echo "  Веб-панель доступна через Telegram бота (кнопка '🌐 Веб-панель' в админ-панели)"
echo "  FastAPI backend работает на порту 8889"
echo ""

