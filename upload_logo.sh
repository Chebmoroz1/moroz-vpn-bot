#!/bin/bash
# Скрипт для загрузки логотипа на сервер

SERVER="root@194.26.27.31"
LOGO_FILE="logo.png"

if [ ! -f "$LOGO_FILE" ]; then
    echo "❌ Файл $LOGO_FILE не найден в текущей директории"
    echo "Пожалуйста, поместите файл logo.png в текущую директорию и запустите скрипт снова"
    exit 1
fi

echo "📤 Загрузка логотипа на сервер..."
scp "$LOGO_FILE" "$SERVER:/root/"

if [ $? -eq 0 ]; then
    echo "✅ Логотип успешно загружен на сервер"
    echo "🔄 Перезапуск бота..."
    ssh "$SERVER" "systemctl restart vpn-bot"
    echo "✅ Готово! Отправьте /start боту для проверки"
else
    echo "❌ Ошибка при загрузке логотипа"
    exit 1
fi

