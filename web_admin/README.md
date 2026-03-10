# Веб-панель администрирования VPN Bot

Веб-панель для администрирования VPN Bot на базе FastAPI + React.

## Структура проекта

```
web_admin/
├── backend/
│   └── main.py          # FastAPI backend
├── frontend/
│   └── (React приложение будет здесь)
└── README.md
```

## Backend (FastAPI)

### Установка и запуск

1. Установите зависимости:
```bash
pip install fastapi uvicorn[standard] pydantic
```

2. Запустите FastAPI сервер:
```bash
cd web_admin/backend
python main.py
```

Или используйте uvicorn напрямую:
```bash
uvicorn main:app --host 0.0.0.0 --port 8889 --reload
```

### API Endpoints

**Авторизация:**
- `POST /api/auth/token` - Генерация токена для веб-панели
- `GET /api/auth/verify` - Проверка токена

**Пользователи:**
- `GET /api/users` - Список пользователей (параметры: skip, limit)
- `GET /api/users/{user_id}` - Информация о пользователе
- `POST /api/users` - Создание нового пользователя
- `PUT /api/users/{user_id}` - Обновление пользователя
- `DELETE /api/users/{user_id}` - Удаление пользователя (soft delete)

**Статистика трафика:**
- `GET /api/traffic` - Статистика трафика (параметры: user_id, start_date, end_date)

**Ключи:**
- `GET /api/keys` - Список ключей (параметры: user_id, skip, limit)
- `PUT /api/keys/{key_id}/activate` - Активация ключа
- `PUT /api/keys/{key_id}/deactivate` - Деактивация ключа
- `DELETE /api/keys/{key_id}` - Удаление ключа

### Авторизация

1. В Telegram боте нажмите "⚙️ Админ-панель" → "🌐 Веб-панель"
2. Бот сгенерирует токен и отправит ссылку на веб-панель
3. Токен действителен 24 часа

## Frontend (React)

### Установка

1. Установите Node.js и npm
2. Перейдите в директорию frontend:
```bash
cd web_admin/frontend
```

3. Установите зависимости:
```bash
npm install
```

### Запуск для разработки

```bash
cd web_admin/frontend
npm start
```

Приложение будет доступно на `http://localhost:3000`

**Примечание:** Frontend уже настроен и готов к использованию. Все необходимые файлы созданы.

## Развертывание

### Backend

Создайте systemd сервис для FastAPI backend:

```ini
[Unit]
Description=VPN Bot Web Admin Backend
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/vpn-bot/web_admin/backend
ExecStart=/usr/bin/python3 /opt/vpn-bot/web_admin/backend/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Frontend

Соберите production версию React приложения:

```bash
cd web_admin/frontend
npm run build
```

Настройте Nginx для раздачи статических файлов и проксирования API запросов:

```nginx
server {
    listen 80;
    server_name admin.moroz.myftp.biz;

    # React frontend
    location / {
        root /opt/vpn-bot/web_admin/frontend/build;
        try_files $uri $uri/ /index.html;
    }

    # FastAPI backend
    location /api {
        proxy_pass http://127.0.0.1:8889;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## Разработка

### Добавление новых API endpoints

1. Добавьте endpoint в `backend/main.py`
2. Добавьте Pydantic модели для запросов/ответов
3. Обновите документацию

### Добавление новых страниц

1. Создайте компонент в `frontend/src/components/`
2. Добавьте маршрут в `frontend/src/App.tsx`
3. Добавьте ссылку в навигацию

## Примечания

- Токены хранятся в памяти (admin_tokens dict). В продакшене использовать Redis или БД
- CORS настроен для всех доменов (`allow_origins=["*"]`). В продакшене указать конкретные домены
- Backend использует порт 8889 (по умолчанию)
- Frontend использует порт 3000 для разработки

