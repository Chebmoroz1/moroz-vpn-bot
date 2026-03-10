# Логика создания нового пользователя и запроса активации

## 📋 Общая схема процесса

```
Пользователь → /start → Создание записи → Меню неактивного пользователя → Запрос активации → Автоверификация/Ручная активация
```

---

## 🔄 Детальный процесс

### Шаг 1: Пользователь запускает бота (`/start`)

**Файл:** `bot.py`, функция `start_command()` (строки 81-122)

```python
async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Получаем данные пользователя из Telegram
    user = update.effective_user
    
    # 2. Ищем пользователя в БД по telegram_id
    db_user = db.query(User).filter(User.telegram_id == user.id).first()
    
    # 3. Если пользователь НЕ найден → создаем нового
    if not db_user:
        await self._request_phone_number(update, context)
        return
    
    # 4. Если пользователь найден, но неактивен → показываем меню
    if not db_user.is_active:
        await self._show_inactive_user_menu(update, context, db_user)
        return
```

---

### Шаг 2: Создание нового пользователя

**Файл:** `bot.py`, функция `_request_phone_number()` (строки 124-156)

Когда пользователь не найден в БД, создается новая запись:

```python
async def _request_phone_number(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, не создан ли уже пользователь
    db_user = db.query(User).filter(User.telegram_id == user.id).first()
    
    if not db_user:
        # Создаем нового пользователя (НЕАКТИВНОГО)
        new_user = User(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name or "Неавторизованный",
            last_name=user.last_name,
            is_active=False,              # ⚠️ НЕАКТИВЕН по умолчанию
            is_admin=(user.id == ADMIN_ID),
            max_keys=0,                   # Нет доступа до активации
            activation_requested=False,   # Запрос еще не отправлен
            activation_requested_at=None  # Дата запроса отсутствует
        )
        db.add(new_user)
        db.commit()
    
    # Показываем меню для неактивных пользователей
    await self._show_inactive_user_menu(update, context, db_user)
```

**Важно:** Новый пользователь создается с `is_active=False`, что означает:
- ❌ Не может создавать VPN ключи
- ❌ Не может использовать функции бота
- ✅ Может запросить активацию
- ✅ Может купить доступ

---

### Шаг 3: Меню неактивного пользователя

**Файл:** `bot.py`, функция `_show_inactive_user_menu()` (строки 2095-2151)

Пользователь видит меню с опциями:

```python
async def _show_inactive_user_menu(self, update, context, db_user):
    text = (
        "⚠️ Ваш аккаунт неактивен\n\n"
        "Выберите действие:\n"
        "• 💳 Купить доступ - приобрести VPN ключи"
    )
    
    # Логика показа кнопки "Запросить активацию":
    # Показываем кнопку, если:
    # - Запрос еще не отправлен (activation_requested = False и activation_requested_at = None)
    # - ИЛИ запрос отправлен, но еще не обработан (activation_requested = True)
    # НЕ показываем, если запрос был отклонен (activation_requested = False и activation_requested_at != None)
    
    if db_user.activation_requested:
        text += "\n• ⏳ Запрос активации отправлен - ожидайте ответа администратора"
    elif show_activation_button:
        text += "\n• 🔓 Активировать аккаунт - запросить активацию у администратора"
    
    keyboard = [
        [InlineKeyboardButton("💳 Купить доступ", callback_data="purchase_menu")],
    ]
    
    if show_activation_button:
        keyboard.append([InlineKeyboardButton("🔓 Запросить активацию", callback_data="request_activation")])
```

**Кнопки в меню:**
1. 💳 **Купить доступ** - переход к оплате VPN ключей
2. 🔓 **Запросить активацию** - отправка запроса администратору (если доступна)
3. 📱 **Предоставить телефон** - для автоверификации

---

### Шаг 4: Обработка запроса активации

**Файл:** `bot.py`, функция `_handle_request_activation()` (строки 2153-2311)

Когда пользователь нажимает "🔓 Запросить активацию":

#### 4.1. Автоверификация (проверка в базе данных)

Система пытается найти активного пользователя по следующим критериям (в порядке приоритета):

**A. По telegram_id:**
```python
found_user = db.query(User).filter(
    User.telegram_id == db_user.telegram_id,
    User.id != db_user.id,  # Исключаем текущего пользователя
    User.is_active == True,
    User.is_deleted == False
).first()
```

**B. По номеру телефона:**
```python
if not found_user and db_user.phone_number:
    normalized_phone = contacts_manager._normalize_phone(db_user.phone_number)
    found_user = db.query(User).filter(
        User.phone_number == normalized_phone,
        User.id != db_user.id,
        User.is_active == True,
        User.is_deleted == False
    ).first()
```

**C. По username:**
```python
if not found_user and db_user.username:
    username_normalized = db_user.username.lstrip('@').lower()
    # Сравниваем с активными пользователями
```

#### 4.2. Если найдено совпадение → Автоверификация

```python
if found_user:
    # Активируем текущего пользователя
    db_user.is_active = True
    db_user.max_keys = found_user.max_keys  # Копируем лимит ключей
    db_user.activation_requested = False
    db_user.activation_requested_at = None
    
    # Копируем недостающие данные из найденного пользователя
    if not db_user.phone_number and found_user.phone_number:
        db_user.phone_number = found_user.phone_number
    # ... и т.д.
    
    # Показываем сообщение об успехе
    welcome_text = (
        "✅ Автоверификация успешна!\n\n"
        "Вы есть в записной книжке Алексея Морозова, "
        "и вам положен доступ к VPN бесплатно!\n\n"
        "Теперь вы можете создавать VPN ключи."
    )
    
    # Показываем главное меню
    await self._show_main_menu(update, context, db_user)
    return
```

**Результат:** Пользователь активирован автоматически, может сразу использовать бота.

#### 4.3. Если совпадение НЕ найдено → Ручная активация

```python
# Если не найдено совпадение - отправляем запрос администратору
db_user.activation_requested = True
db_user.activation_requested_at = datetime.now()
db.commit()

# Показываем сообщение пользователю
text = (
    "🔓 Запрос активации аккаунта\n\n"
    "Ваш запрос на активацию отправлен администратору.\n"
    "После активации вы получите уведомление.\n\n"
    "Вы также можете купить доступ, чтобы получить VPN ключи сразу."
)

# Отправляем уведомление администратору
admin_text = (
    f"🔓 Запрос на активацию аккаунта\n\n"
    f"Пользователь: {display_name}\n"
    f"Telegram ID: {db_user.telegram_id}\n"
    f"Телефон: {db_user.phone_number or 'не указан'}\n\n"
    f"ID пользователя в БД: {db_user.id}"
)

admin_keyboard = [
    [
        InlineKeyboardButton("✅ Активировать", callback_data=f"admin_activate_user:{db_user.id}"),
        InlineKeyboardButton("❌ Отказать", callback_data=f"admin_reject_user:{db_user.id}")
    ]
]
```

**Результат:** 
- Пользователь видит сообщение о том, что запрос отправлен
- Администратор получает уведомление с кнопками для активации/отказа

---

### Шаг 5: Активация администратором

**Файл:** `bot.py`, функция `_handle_admin_activate_user()` (строки 2534-2565)

Когда администратор нажимает "✅ Активировать":

```python
async def _handle_admin_activate_user(self, update, context, admin_user, target_user_id):
    target_user = db.query(User).filter(User.id == target_user_id).first()
    
    # Активируем пользователя
    target_user.is_active = True
    target_user.activation_requested = False
    target_user.activation_requested_at = None
    db.commit()
    
    # Отправляем уведомление пользователю
    await context.bot.send_message(
        chat_id=target_user.telegram_id,
        text="✅ Ваш аккаунт активирован! Теперь вы можете использовать бота."
    )
```

**Результат:** Пользователь получает уведомление и может использовать бота.

---

### Шаг 6: Отказ в активации

**Файл:** `bot.py`, функция `_handle_admin_reject_user()` (строки 2567-2602)

Когда администратор нажимает "❌ Отказать":

```python
async def _handle_admin_reject_user(self, update, context, admin_user, target_user_id):
    target_user = db.query(User).filter(User.id == target_user_id).first()
    
    # При отказе устанавливаем activation_requested = False, но оставляем activation_requested_at
    # Это позволяет отличить отклоненный запрос от нового пользователя
    if target_user.activation_requested_at is None:
        target_user.activation_requested_at = datetime.now()
    target_user.activation_requested = False
    db.commit()
    
    # Отправляем уведомление пользователю
    await context.bot.send_message(
        chat_id=target_user.telegram_id,
        text="❌ Ваш запрос на активацию отклонен. Вы можете купить доступ или обратиться к администратору."
    )
```

**Результат:** 
- Пользователь получает уведомление об отказе
- Кнопка "Запросить активацию" больше не показывается (так как `activation_requested = False` и `activation_requested_at != None`)

---

## 🔑 Ключевые поля в модели User

**Файл:** `database.py`, класс `User` (строки 17-35)

```python
class User(Base):
    is_active = Column(Boolean, default=True)  # Активен ли пользователь
    max_keys = Column(Integer, default=1)      # Лимит VPN ключей
    activation_requested = Column(Boolean, default=False)  # Запрошена ли активация
    activation_requested_at = Column(DateTime, nullable=True)  # Дата запроса
```

### Логика состояний:

| `is_active` | `activation_requested` | `activation_requested_at` | Состояние |
|-------------|----------------------|--------------------------|-----------|
| `False` | `False` | `None` | Новый пользователь, может запросить активацию |
| `False` | `True` | `datetime` | Запрос отправлен, ожидает ответа |
| `False` | `False` | `datetime` | Запрос отклонен, кнопка не показывается |
| `True` | `False` | `None` | Пользователь активирован |

---

## 📊 Диаграмма состояний

```
┌─────────────────┐
│  Новый          │
│  пользователь   │
│  /start         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Создание       │
│  записи в БД    │
│  is_active=False│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Меню           │
│  неактивного    │
│  пользователя   │
└────────┬────────┘
         │
         │ Нажатие "Запросить активацию"
         ▼
    ┌────────┐
    │ Проверка│
    │ в БД   │
    └───┬────┘
        │
    ┌───┴────┐
    │        │
    ▼        ▼
┌──────┐  ┌──────────┐
│Найдено│  │Не найдено│
└───┬──┘  └────┬─────┘
    │          │
    │          ▼
    │    ┌──────────────┐
    │    │Запрос админу │
    │    │activation_   │
    │    │requested=True│
    │    └──────┬───────┘
    │           │
    │      ┌────┴────┐
    │      │         │
    │      ▼         ▼
    │  ┌──────┐  ┌──────┐
    │  │Акти- │  │Отказ │
    │  │виро- │  │      │
    │  │ван   │  │      │
    │  └──┬───┘  └──┬───┘
    │     │         │
    └─────┴─────────┘
            │
            ▼
    ┌───────────────┐
    │ is_active=True│
    │ Главное меню  │
    └───────────────┘
```

---

## 🎯 Особенности реализации

### 1. Автоверификация
- Система автоматически проверяет наличие пользователя в БД
- Проверка по `telegram_id`, `phone_number`, `username`
- Если найдено совпадение → автоматическая активация

### 2. Защита от дублирования
- При создании нового пользователя проверяется существование по `telegram_id`
- При автоверификации исключается текущий пользователь (`User.id != db_user.id`)

### 3. Умная логика показа кнопки
- Кнопка "Запросить активацию" показывается только если:
  - Запрос еще не отправлен
  - ИЛИ запрос отправлен, но еще не обработан
- Кнопка НЕ показывается, если запрос был отклонен

### 4. Копирование данных
- При автоверификации копируются недостающие данные из найденного пользователя
- Копируется `max_keys` (лимит ключей)

---

## 📝 Примеры сценариев

### Сценарий 1: Новый пользователь, нет в базе
1. Пользователь: `/start`
2. Создается запись: `is_active=False`, `activation_requested=False`
3. Показывается меню с кнопкой "Запросить активацию"
4. Пользователь нажимает "Запросить активацию"
5. Автоверификация не находит совпадений
6. Отправляется запрос администратору
7. Администратор активирует → пользователь получает уведомление

### Сценарий 2: Пользователь есть в базе (автоверификация)
1. Пользователь: `/start`
2. Создается запись: `is_active=False`
3. Показывается меню с кнопкой "Запросить активацию"
4. Пользователь нажимает "Запросить активацию"
5. Автоверификация находит активного пользователя по телефону
6. Текущий пользователь активируется автоматически
7. Показывается главное меню

### Сценарий 3: Отказ в активации
1. Пользователь запрашивает активацию
2. Администратор нажимает "❌ Отказать"
3. `activation_requested = False`, `activation_requested_at = datetime.now()`
4. Пользователь получает уведомление об отказе
5. Кнопка "Запросить активацию" больше не показывается
6. Пользователь может только купить доступ

---

## 🔧 Технические детали

### Обработка callback
**Файл:** `bot.py`, функция `callback_handler()` (строки 580-781)

```python
elif data == "request_activation":
    await self._handle_request_activation(update, context, db_user)
```

### Проверка активности
**Файл:** `bot.py`, функция `start_command()` (строки 109-113)

```python
if not db_user.is_active:
    await self._show_inactive_user_menu(update, context, db_user)
    return
```

---

**Составлено:** 23 ноября 2025

