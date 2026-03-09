"""
Main Telegram bot module for MOROZ VPN Bot.

This file contains the VPNBot application bootstrap:
- logging configuration
- database initialization
- Application setup (python-telegram-bot v20)
- basic /start and main menu handlers

Further business logic (auth flow, key management, admin panel) is implemented
on top of this core.
"""

import asyncio
import logging
import re
import sys
from datetime import datetime
from typing import Final, Optional

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN as ENV_BOT_TOKEN, ADMIN_ID as ENV_ADMIN_ID
from config_manager import ConfigManager
from database import init_db, get_db_session, User, VPNKey, UserMessage
from traffic_manager import TrafficManager
from vpn_manager import VPNManager


# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Helpers for config values
# ──────────────────────────────────────────────

def get_bot_token() -> str:
    """Get BOT_TOKEN from DB config or environment."""
    token = ConfigManager.get("BOT_TOKEN")
    if token:
        return token
    return ENV_BOT_TOKEN


def get_admin_id() -> int:
    """Get ADMIN_ID from DB config or environment."""
    # DB has priority
    admin_str = ConfigManager.get("ADMIN_ID")
    if not admin_str:
        admin_str = str(ENV_ADMIN_ID or "0")
    try:
        return int(admin_str)
    except (TypeError, ValueError):
        return 0


MAIN_MENU_BUTTON: Final[str] = "📱 Меню"


def build_main_keyboard() -> ReplyKeyboardMarkup:
    """Build main menu keyboard with all core actions and the menu button."""
    keyboard = [
        [KeyboardButton(MAIN_MENU_BUTTON)],
        [KeyboardButton("🔐 Получить AmneziaWG ключ")],
        [KeyboardButton("📋 Мои ключи"), KeyboardButton("📊 Статус подключения")],
        [KeyboardButton("🔑 Запросить ещё ключ")],
        [KeyboardButton("❓ Задать вопрос"), KeyboardButton("🐛 Сообщить о проблеме")],
        [KeyboardButton("ℹ️ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def build_inactive_user_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard for non-active users."""
    keyboard = [
        [KeyboardButton("🔓 Запросить активацию")],
        [KeyboardButton("📱 Предоставить телефон")],
        [KeyboardButton("❓ Задать вопрос")],
        [KeyboardButton(MAIN_MENU_BUTTON)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def build_admin_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard for admin panel sections."""
    keyboard = [
        [KeyboardButton("👥 Пользователи"), KeyboardButton("🔑 Все ключи")],
        [KeyboardButton("📨 Входящие"), KeyboardButton("📢 Рассылка")],
        [KeyboardButton("🔓 Открытый доступ"), KeyboardButton("⚙️ Настройки")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("🔄 Синхронизировать ключи")],
        [KeyboardButton("⬅️ Назад"), KeyboardButton(MAIN_MENU_BUTTON)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def normalize_phone(raw: str) -> Optional[str]:
    """
    Normalize Russian phone number according to TZ rules.

    Examples:
        +79001234567 -> +79001234567
        89001234567  -> +79001234567
        79001234567  -> +79001234567
        +89001234567 -> +79001234567
    """
    if not raw:
        return None

    digits = re.sub(r"[^\d+]", "", raw)
    # already in +7XXXXXXXXXX
    if digits.startswith("+7") and len(digits) == 12:
        return digits
    # +8XXXXXXXXXX -> +7XXXXXXXXXX
    if digits.startswith("+8") and len(digits) == 12:
        return "+7" + digits[2:]
    # 8900... or 7900...
    if digits.startswith("8") and len(digits) == 11:
        return "+7" + digits[1:]
    if digits.startswith("7") and len(digits) == 11:
        return "+7" + digits[1:]

    # If nothing matched, return as-is for now
    if digits.startswith("+") and len(digits) >= 11:
        return digits
    return None


# ──────────────────────────────────────────────
# Core bot class
# ──────────────────────────────────────────────


class VPNBot:
    """Wrapper around python-telegram-bot Application."""

    def __init__(self) -> None:
        init_db()

        # In‑memory state for simple multi‑step user flows
        # key: user.id, value: {"kind": ..., ...}
        # kinds: question, problem, key_request, broadcast
        self._pending_inputs: dict[int, dict] = {}

        token = get_bot_token()
        if not token:
            logger.error("BOT_TOKEN is not configured. Set it in .env or app_config.")
            raise RuntimeError("BOT_TOKEN is missing")

        self.application: Application = (
            ApplicationBuilder()
            .token(token)
            .concurrent_updates(True)
            .build()
        )

        # Core services
        self.vpn_manager = VPNManager()

        # Register handlers
        self._register_handlers()

        # Global error handler
        self.application.add_error_handler(self._application_error_handler)

        logger.info("VPNBot initialized (admin_id=%s)", get_admin_id())

    # ──────────────────────────────────────
    # Handlers registration
    # ──────────────────────────────────────

    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("menu", self.cmd_menu))

        # Contacts for phone-based auth
        self.application.add_handler(
            MessageHandler(filters.CONTACT, self.handle_contact),
        )

        # Text buttons / main menu actions
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.handle_text_buttons,
            )
        )

        # Callback queries (inline keyboards)
        self.application.add_handler(CallbackQueryHandler(self._callback_router))

    # ──────────────────────────────────────
    # Commands
    # ──────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Basic /start handler.

        Implements registration & basic auth flow:
        - find or create user by telegram_id
        - update profile fields
        - apply open-access (auth bypass) rules
        - sync is_admin flag with ADMIN_ID
        - show appropriate menu
        """
        tg_user = update.effective_user
        if tg_user is None:
            return

        with get_db_session() as session:
            user: Optional[User] = (
                session.query(User)
                .filter(User.telegram_id == tg_user.id)
                .first()
            )

            if not user:
                user = User(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                )
                session.add(user)
                logger.info("Created new user id=%s (tg_id=%s)", user.id, tg_user.id)
            else:
                # Update profile data on every /start
                user.username = tg_user.username
                user.first_name = tg_user.first_name
                user.last_name = tg_user.last_name

            # Open-access (auth bypass) mode
            if not user.is_active and ConfigManager.is_auth_bypass_active():
                max_keys = ConfigManager.get_auth_bypass_max_keys()
                user.is_active = True
                user.max_keys = max_keys
                user.activation_requested = False
                logger.info(
                    "User %s auto-activated via auth bypass (max_keys=%d)",
                    user.id,
                    max_keys,
                )

            # Admin detection / sync
            admin_id = get_admin_id()
            user.is_admin = bool(admin_id and tg_user.id == admin_id)

            # Admin should always have active status and a sane key limit
            if user.is_admin and not user.is_active:
                max_keys = user.max_keys or ConfigManager.get_auth_bypass_max_keys() or 1
                user.is_active = True
                user.max_keys = max_keys
                user.activation_requested = False
                logger.info(
                    "Admin user %s auto-activated (tg_id=%s, max_keys=%d)",
                    user.id,
                    tg_user.id,
                    max_keys,
                )

            is_active = user.is_active
            is_admin = user.is_admin

        # Now send appropriate menu
        if is_active:
            await self._send_active_menu(update.effective_message, is_admin)
        else:
            await self._send_inactive_menu(update.effective_message)

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Entry point to the main menu (context-aware for active/inactive users)."""
        tg_user = update.effective_user
        if tg_user is None:
            return

        with get_db_session() as session:
            user: Optional[User] = (
                session.query(User)
                .filter(User.telegram_id == tg_user.id)
                .first()
            )

            if not user:
                # If somehow user is missing, delegate to /start
                await self.cmd_start(update, context)
                return

            is_active = user.is_active
            is_admin = user.is_admin

        if is_active:
            await self._send_active_menu(update.effective_message, is_admin)
        else:
            await self._send_inactive_menu(update.effective_message)

    async def _send_inactive_menu(self, message: Message) -> None:
        """Show menu for non-active users."""
        lines = [
            "👋 Привет! Твой аккаунт пока не активирован.",
            "",
            "Доступные действия:",
            "🔓 Запросить активацию",
            "📱 Предоставить телефон",
            "❓ Задать вопрос администратору",
        ]
        await message.reply_text(
            "\n".join(lines),
            reply_markup=build_inactive_user_keyboard(),
        )

    async def _send_active_menu(self, message: Message, is_admin: bool) -> None:
        """Show main menu for active users (admin sees extra entry)."""
        lines = [
            "📱 Главное меню",
            "🔐 Получить AmneziaWG ключ",
            "📋 Мои ключи",
            "📊 Статус подключения",
            "🔑 Запросить ещё ключ",
            "❓ Задать вопрос",
            "🐛 Сообщить о проблеме",
            "ℹ️ Помощь",
        ]
        if is_admin:
            lines.append("⚙️ Админ-панель")

        await message.reply_text(
            "\n".join(lines),
            reply_markup=build_main_keyboard(),
        )

    # ──────────────────────────────────────
    # Text / contact handlers
    # ──────────────────────────────────────

    async def handle_text_buttons(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle plain-text buttons for inactive users."""
        message = update.effective_message
        if not message or not message.text:
            return

        text = message.text.strip()
        tg_user = update.effective_user
        if tg_user is None:
            return

        with get_db_session() as session:
            user: Optional[User] = (
                session.query(User)
                .filter(User.telegram_id == tg_user.id)
                .first()
            )

            if not user:
                # Fallback to /start logic if user record is missing
                await self.cmd_start(update, context)
                return

            # Check if we are waiting for a follow‑up text from this user
            pending = self._pending_inputs.pop(user.id, None)

            # Global "📱 Меню" button: always open the appropriate menu and
            # effectively cancel any pending multi-step flow.
            if text == MAIN_MENU_BUTTON:
                await self.cmd_menu(update, context)
                return

            if pending and message.text:
                # Store user message in DB according to the pending kind
                if kind in {"question", "problem", "key_request"}:
                    text_to_store = message.text.strip()
                    if len(text_to_store) > 1000:
                        text_to_store = text_to_store[:1000]

                    message_type = kind
                    # Optionally prefix problem with a category label when present later
                    prefix = pending.get("prefix")
                    if prefix:
                        text_to_store = f"[{prefix}] {text_to_store}"

                    with get_db_session() as session:
                        user_obj: Optional[User] = (
                            session.query(User).filter(User.id == user.id).first()
                        )
                        if not user_obj:
                            # Should not happen, but be safe
                            await message.reply_text(
                                "Не удалось сохранить сообщение, попробуй ещё раз.",
                                reply_markup=build_main_keyboard()
                                if user.is_active
                                else build_inactive_user_keyboard(),
                            )
                            return

                        user_msg = UserMessage(
                            user_id=user.id,
                            message_type=message_type,
                            message_text=text_to_store,
                        )
                        session.add(user_msg)
                        session.flush()
                        msg_id = user_msg.id

                    # Notify admin asynchronously about the new message
                    await self._notify_admin_new_message(
                        user=user,
                        message_type=message_type,
                        message_text=text_to_store,
                        msg_id=msg_id,
                    )

                    if kind == "question":
                        await message.reply_text(
                            "Вопрос отправлен администратору. "
                            "Ответ придёт в личные сообщения, как только админ его обработает.",
                            reply_markup=build_main_keyboard()
                            if user.is_active
                            else build_inactive_user_keyboard(),
                        )
                    elif kind == "problem":
                        await message.reply_text(
                            "Сообщение о проблеме отправлено администратору.",
                            reply_markup=build_main_keyboard()
                            if user.is_active
                            else build_inactive_user_keyboard(),
                        )
                    elif kind == "key_request":
                        await message.reply_text(
                            "Запрос на дополнительный ключ отправлен администратору.",
                            reply_markup=build_main_keyboard(),
                        )
                    return
                if kind == "broadcast" and user.is_admin:
                    # Admin broadcast: send this text to all active users
                    text_to_send = message.text.strip()
                    if not text_to_send:
                        await message.reply_text(
                            "Текст рассылки пустой, попробуй ещё раз.",
                            reply_markup=build_admin_keyboard(),
                        )
                        return

                    sent = 0
                    with get_db_session() as session:
                        recipients = (
                            session.query(User)
                            .filter(
                                User.is_active.is_(True),
                                User.telegram_id.isnot(None),
                                User.is_deleted.is_(False),
                            )
                            .all()
                        )

                    for u in recipients:
                        try:
                            await self.application.bot.send_message(
                                chat_id=u.telegram_id,
                                text=text_to_send,
                                parse_mode="Markdown",
                            )
                            sent += 1
                        except Exception as e:
                            logger.warning(
                                "Failed to send broadcast to %s: %s", u.telegram_id, e
                            )

                    await message.reply_text(
                        f"Рассылка завершена. Сообщение отправлено {sent} пользователям.",
                        reply_markup=build_admin_keyboard(),
                    )
                    return

            is_active = user.is_active

            # Inactive user buttons
            if not is_active:
                if text == "🔓 Запросить активацию":
                    # Mark request and create UserMessage for admin
                    user.activation_requested = True
                    msg = UserMessage(
                        user_id=user.id,
                        message_type="activation",
                        message_text="Запрос активации аккаунта",
                    )
                    session.add(msg)
                    session.flush()
                    logger.info(
                        "User %s requested activation (telegram_id=%s)",
                        user.id,
                        tg_user.id,
                    )

                    # Notify admin with user details and inline approval controls.
                    await self._notify_admin_activation_request(
                        user=user,
                        msg_id=msg.id,
                    )

                    await message.reply_text(
                        "Запрос на активацию отправлен администратору. "
                        "Вы получите уведомление после рассмотрения.",
                        reply_markup=build_inactive_user_keyboard(),
                    )
                    return

                if text == "📱 Предоставить телефон":
                    await message.reply_text(
                        "Пожалуйста, отправь свой контакт через кнопку Telegram "
                        "«Поделиться номером телефона».",
                        reply_markup=build_inactive_user_keyboard(),
                    )
                    return

                if text == "❓ Задать вопрос":
                    await message.reply_text(
                        "Отправь свой вопрос одним сообщением (до 1000 символов).",
                        reply_markup=build_inactive_user_keyboard(),
                    )
                    # Next free‑text message from this user will be stored as a question
                    self._pending_inputs[user.id] = {"kind": "question"}
                    return

            # Active user buttons (core VPN flows)
            if is_active:
                # Admin panel entry
                if user.is_admin and text == "⚙️ Админ-панель":
                    await self._admin_show_panel(message)
                    return

                # Admin panel actions
                if user.is_admin:
                    if text == "⬅️ Назад":
                        await self._send_active_menu(message, True)
                        return
                    if text == "🔄 Синхронизировать ключи":
                        await self._admin_sync_keys(message)
                        return
                    if text == "📊 Статистика":
                        await self._admin_show_stats(message)
                        return
                    if text == "📨 Входящие":
                        await self._admin_show_inbox(message)
                        return
                    if text == "📢 Рассылка":
                        await self._admin_start_broadcast(message)
                        return
                    if text == "🔓 Открытый доступ":
                        await self._admin_auth_bypass_menu(message)
                        return
                    if text == "👥 Пользователи":
                        await self._admin_list_users(message)
                        return
                    if text == "🔑 Все ключи":
                        await self._admin_list_keys(message)
                        return
                    if text == "⚙️ Настройки":
                        await self._admin_show_settings_hint(message)
                        return

                if text == "🔐 Получить AmneziaWG ключ":
                    await self._handle_create_key(user, message)
                    return
                if text == "📋 Мои ключи":
                    await self._handle_list_keys(user, message)
                    return
                if text == "📊 Статус подключения":
                    await self._handle_status(user, message)
                    return
                if text == "🔑 Запросить ещё ключ":
                    await self._handle_extra_key_request(user, message)
                    return
                if text == "❓ Задать вопрос":
                    await message.reply_text(
                        "Напиши свой вопрос одним сообщением (до 1000 символов).",
                        reply_markup=build_main_keyboard(),
                    )
                    self._pending_inputs[user.id] = {"kind": "question"}
                    return
                if text == "🐛 Сообщить о проблеме":
                    await message.reply_text(
                        "Кратко опиши проблему одним сообщением (до 1000 символов).",
                        reply_markup=build_main_keyboard(),
                    )
                    self._pending_inputs[user.id] = {"kind": "problem"}
                    return
                if text == "ℹ️ Помощь":
                    await message.reply_text(
                        "Этот бот помогает получать и управлять VPN‑ключами AmneziaWG.\n\n"
                        "Через главное меню ты можешь:\n"
                        "• создать новый ключ\n"
                        "• посмотреть текущие ключи\n"
                        "• проверить статус подключения и трафик\n"
                        "• запросить дополнительный ключ\n"
                        "• задать вопрос или сообщить о проблеме администратору.",
                        reply_markup=build_main_keyboard(),
                    )
                    return

    async def handle_contact(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle phone-number based authorization."""
        tg_user = update.effective_user
        contact = update.effective_message.contact if update.effective_message else None

        if tg_user is None or contact is None:
            return

        # Soft check: when Telegram provides contact.user_id, ensure users
        # only share their own contact, not someone else's.
        if getattr(contact, "user_id", None) and contact.user_id != tg_user.id:
            await update.effective_message.reply_text(
                "Пожалуйста, отправь именно свой номер через кнопку "
                "«Поделиться номером телефона», а не контакт другого человека.",
                reply_markup=build_inactive_user_keyboard(),
            )
            return

        normalized = normalize_phone(contact.phone_number)
        if not normalized:
            await update.effective_message.reply_text(
                "Не удалось распознать номер телефона. Попробуй ещё раз.",
                reply_markup=build_inactive_user_keyboard(),
            )
            return

        with get_db_session() as session:
            # Current user by telegram_id
            current: Optional[User] = (
                session.query(User)
                .filter(User.telegram_id == tg_user.id)
                .first()
            )

            # Possible existing user by phone
            by_phone: Optional[User] = (
                session.query(User)
                .filter(User.phone_number == normalized)
                .first()
            )

            target = current or by_phone
            if not target:
                target = User(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                    phone_number=normalized,
                )
                session.add(target)
            else:
                # Merge data
                target.telegram_id = tg_user.id
                target.username = tg_user.username
                target.first_name = tg_user.first_name
                target.last_name = tg_user.last_name
                target.phone_number = normalized

            logger.info(
                "Updated phone for user id=%s: %s",
                target.id,
                normalized,
            )

            is_active = target.is_active

        # Inform user about status
        if is_active:
            await update.effective_message.reply_text(
                "Номер телефона подтверждён, доступ к VPN уже активирован.",
                reply_markup=build_main_keyboard(),
            )
        else:
            await update.effective_message.reply_text(
                "Номер телефона подтверждён. Если аккаунт ещё не активирован, "
                "нажми «🔓 Запросить активацию».",
                reply_markup=build_inactive_user_keyboard(),
            )

    # ──────────────────────────────────────
    # VPN key management helpers
    # ──────────────────────────────────────

    async def _handle_create_key(self, user: User, message: Message) -> None:
        """Create new VPN key for the user respecting max_keys limit."""
        # Check limits
        with get_db_session() as session:
            active_count = (
                session.query(VPNKey)
                .filter(VPNKey.user_id == user.id, VPNKey.is_active.is_(True))
                .count()
            )
            max_keys = user.max_keys or 0

        if active_count >= max_keys:
            await message.reply_text(
                f"Лимит ключей исчерпан: {active_count} из {max_keys}. "
                "Можно запросить дополнительный ключ через меню.",
                reply_markup=build_main_keyboard(),
            )
            return

        await message.reply_text("Создаю новый VPN ключ, подожди несколько секунд…")

        # Protect the full key creation flow with a global timeout so that
        # transient Docker / network issues do not block the bot forever.
        try:
            result = await asyncio.wait_for(
                self.vpn_manager.create_key(user),
                timeout=60,
            )
        except asyncio.TimeoutError:
            logger.error("Key creation timed out for user id=%s", user.id)
            await message.reply_text(
                "Создание ключа занимает слишком много времени и было прервано. "
                "Попробуй ещё раз чуть позже.",
                reply_markup=build_main_keyboard(),
            )
            return
        if not result:
            await message.reply_text(
                "Ошибка при генерации ключа. Подробнее смотри лог на сервере.",
                reply_markup=build_main_keyboard(),
            )
            return

        # Send files and config
        try:
            await message.reply_document(
                open(result["config_file"], "rb"),
                filename=f"{result['key_name']}.conf",
            )
        except Exception as e:
            logger.warning("Failed to send config file: %s", e)

        try:
            await message.reply_photo(
                open(result["qr_code_file"], "rb"),
                caption="QR-код для быстрой настройки клиента.",
            )
        except Exception as e:
            logger.warning("Failed to send QR image: %s", e)

        await message.reply_text(
            "Ключ успешно создан. Конфигурацию можно сохранить и импортировать в клиент.",
            reply_markup=build_main_keyboard(),
        )

    async def _handle_list_keys(self, user: User, message: Message) -> None:
        """Show list of user's keys with inline delete buttons."""
        with get_db_session() as session:
            keys = (
                session.query(VPNKey)
                .filter(VPNKey.user_id == user.id)
                .order_by(VPNKey.created_at.desc())
                .all()
            )

        if not keys:
            await message.reply_text(
                "У тебя пока нет ни одного VPN ключа.",
                reply_markup=build_main_keyboard(),
            )
            return

        text_lines = ["📋 Твои ключи (нажми кнопку, чтобы удалить):"]
        keyboard_rows = []
        for k in keys:
            status = "🟢" if k.is_active else "🔴"
            text_lines.append(f"{status} {k.key_name} — {k.client_ip or '-'}")
            if k.is_active:
                keyboard_rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"🗑 Удалить {k.key_name}",
                            callback_data=f"delkey:{k.id}",
                        )
                    ]
                )

        await message.reply_text(
            "\n".join(text_lines),
            reply_markup=InlineKeyboardMarkup(keyboard_rows)
            if keyboard_rows
            else build_main_keyboard(),
        )

    async def _handle_status(self, user: User, message: Message) -> None:
        """Show connection status and monthly traffic using TrafficManager."""
        overview = TrafficManager.get_traffic_overview()
        user_stats = TrafficManager.get_user_traffic(user.id, period="month")

        lines = [
            "📊 Статус подключения",
            "",
            f"Всего активных ключей в системе: {overview['total_keys']}",
            f"Активные подключения сейчас: {overview['active_connections']}",
            "",
            "Твой трафик за месяц:",
            f"↓ Получено: {TrafficManager.format_bytes(user_stats['total_received'])}",
            f"↑ Отправлено: {TrafficManager.format_bytes(user_stats['total_sent'])}",
        ]

        if user_stats["keys"]:
            lines.append("")
            lines.append("По ключам:")
            for k in user_stats["keys"]:
                lines.append(
                    f"- {k['key_name']}: "
                    f"{TrafficManager.format_bytes(k['bytes_received'])} ↓ / "
                    f"{TrafficManager.format_bytes(k['bytes_sent'])} ↑"
                )

        await message.reply_text(
            "\n".join(lines),
            reply_markup=build_main_keyboard(),
        )

    async def _handle_extra_key_request(self, user: User, message: Message) -> None:
        """User requests an additional key beyond max_keys."""
        with get_db_session() as session:
            active_count = (
                session.query(VPNKey)
                .filter(VPNKey.user_id == user.id, VPNKey.is_active.is_(True))
                .count()
            )
            max_keys = user.max_keys or 0

        if active_count < max_keys:
            await message.reply_text(
                "У тебя ещё есть свободные слоты для ключей. "
                "Сначала создай ключ через «🔐 Получить AmneziaWG ключ».",
                reply_markup=build_main_keyboard(),
            )
            return

        # Ask user for a short textual reason and store it as a separate message
        await message.reply_text(
            "Ты уже использовал все доступные ключи.\n\n"
            "Кратко напиши, зачем нужен дополнительный ключ (до 1000 символов).",
            reply_markup=build_main_keyboard(),
        )
        self._pending_inputs[user.id] = {"kind": "key_request"}

    # ──────────────────────────────────────
    # Admin panel helpers
    # ──────────────────────────────────────

    async def _admin_show_panel(self, message: Message) -> None:
        """Show top-level admin panel menu."""
        lines = [
            "⚙️ Админ-панель",
            "",
            "Доступные разделы:",
            "👥 Пользователи — список и управление",
            "🔑 Все ключи — обзор и операции",
            "📨 Входящие — запросы и вопросы",
            "📢 Рассылка — сообщения всем пользователям",
            "🔓 Открытый доступ — управление режимом auth bypass",
            "⚙️ Настройки — параметры бота и VPN",
            "📊 Статистика — общая статистика системы",
            "🔄 Синхронизировать ключи — сверка БД и VPN сервера",
        ]
        await message.reply_text("\n".join(lines), reply_markup=build_admin_keyboard())

    async def _admin_sync_keys(self, message: Message) -> None:
        """Run VPN keys sync with server and show summary."""
        await message.reply_text("Запускаю синхронизацию ключей с сервером…")
        summary = await self.vpn_manager.sync_keys_with_server()
        lines = [
            "Синхронизация завершена:",
            f"Всего ключей в БД: {summary['total_db_keys']}",
            f"Всего пиров на сервере: {summary['total_server_peers']}",
            f"Синхронизировано: {summary['synced']}",
            f"Деактивировано (только в БД): {summary['deactivated']}",
            f"Осиротевшие пиpы (только на сервере): {summary['orphaned_peers']}",
        ]
        await message.reply_text("\n".join(lines), reply_markup=build_admin_keyboard())

    async def _admin_show_stats(self, message: Message) -> None:
        """Show basic system statistics for admin."""
        with get_db_session() as session:
            total_users = session.query(User).count()
            active_users = session.query(User).filter(User.is_active.is_(True)).count()
            admins = session.query(User).filter(User.is_admin.is_(True)).count()
            total_keys = session.query(VPNKey).count()

        lines = [
            "📊 Общая статистика",
            f"Пользователи всего: {total_users}",
            f"Активные пользователи: {active_users}",
            f"Администраторов: {admins}",
            f"Всего ключей: {total_keys}",
        ]
        await message.reply_text("\n".join(lines), reply_markup=build_admin_keyboard())

    async def _admin_show_inbox(self, message: Message) -> None:
        """Show latest incoming user messages for admin."""
        with get_db_session() as session:
            msgs = (
                session.query(UserMessage)
                .order_by(UserMessage.created_at.desc())
                .limit(10)
                .all()
            )

        if not msgs:
            await message.reply_text(
                "Новых сообщений от пользователей нет.",
                reply_markup=build_admin_keyboard(),
            )
            return

        type_labels = {
            "question": "❓ Вопрос",
            "problem": "🐛 Проблема",
            "key_request": "🔑 Запрос ключа",
            "other": "📨 Другое",
        }

        lines = ["📨 Последние сообщения:"]
        for m in msgs:
            label = type_labels.get(m.message_type, m.message_type)
            status = m.status or "pending"
            lines.append(
                f"{label} (id={m.id}, user_id={m.user_id}, status={status})\n"
                f"{m.message_text[:120]}{'…' if len(m.message_text) > 120 else ''}"
            )

        await message.reply_text(
            "\n\n".join(lines),
            reply_markup=build_admin_keyboard(),
        )

    async def _admin_start_broadcast(self, message: Message) -> None:
        """Ask admin for broadcast text; next message will be sent to all users."""
        await message.reply_text(
            "Отправь текст рассылки одним сообщением (поддерживается Markdown). "
            "Сообщение будет отправлено всем активным пользователям.",
            reply_markup=build_admin_keyboard(),
        )
        # Mark that the next text from this admin is a broadcast payload
        with get_db_session() as session:
            admin: Optional[User] = (
                session.query(User)
                .filter(User.telegram_id == message.from_user.id)
                .first()
            )
        if admin:
            self._pending_inputs[admin.id] = {"kind": "broadcast"}

    async def _admin_auth_bypass_menu(self, message: Message) -> None:
        """Show current auth bypass status and simple management options."""
        enabled = ConfigManager.get_bool("auth_bypass_enabled", False)
        until = ConfigManager.get("auth_bypass_until")
        max_keys = ConfigManager.get_auth_bypass_max_keys()

        status_line = "✅ Включён" if enabled else "❌ Выключен"
        if enabled and until:
            status_line += f" до {until}"

        lines = [
            "🔓 Режим открытого доступа",
            f"Текущий статус: {status_line}",
            f"Авто-лимит ключей: {max_keys}",
            "",
            "Измени режим через веб-панель (страница Settings) "
            "или с помощью backend API.",
        ]

        await message.reply_text(
            "\n".join(lines),
            reply_markup=build_admin_keyboard(),
        )

    async def _admin_list_users(self, message: Message) -> None:
        """Show a short summary of users for admin."""
        with get_db_session() as session:
            users = (
                session.query(User)
                .order_by(User.created_at.desc())
                .limit(10)
                .all()
            )

        if not users:
            await message.reply_text(
                "Пользователей в базе пока нет.",
                reply_markup=build_admin_keyboard(),
            )
            return

        lines = ["👥 Последние пользователи:"]
        for u in users:
            status = "✅" if u.is_active else "⛔"
            admin_mark = "👑" if u.is_admin else ""
            name = u.nickname or u.username or (u.first_name or "user")
            lines.append(
                f"{status}{admin_mark} {name} (id={u.id}, tg={u.telegram_id}, keys_max={u.max_keys})"
            )

        await message.reply_text(
            "\n".join(lines),
            reply_markup=build_admin_keyboard(),
        )

    async def _admin_list_keys(self, message: Message) -> None:
        """Show short summary of VPN keys for admin."""
        with get_db_session() as session:
            keys = (
                session.query(VPNKey)
                .order_by(VPNKey.created_at.desc())
                .limit(10)
                .all()
            )

        if not keys:
            await message.reply_text(
                "В системе ещё нет VPN ключей.",
                reply_markup=build_admin_keyboard(),
            )
            return

        lines = ["🔑 Последние ключи:"]
        for k in keys:
            status = "🟢" if k.is_active else "🔴"
            lines.append(
                f"{status} {k.key_name} (id={k.id}, user_id={k.user_id}, ip={k.client_ip or '-'})"
            )

        await message.reply_text(
            "\n".join(lines),
            reply_markup=build_admin_keyboard(),
        )

    async def _admin_show_settings_hint(self, message: Message) -> None:
        """Show a hint that advanced settings are managed via web admin."""
        lines = [
            "⚙️ Настройки приложения",
            "",
            "Подробные настройки Telegram-бота и VPN сервера "
            "редактируются через веб-панель администрирования (страница Settings).",
            "Через неё можно менять BOT_TOKEN, ADMIN_ID, параметры VPN и режим открытого доступа.",
        ]
        await message.reply_text(
            "\n".join(lines),
            reply_markup=build_admin_keyboard(),
        )

    # ──────────────────────────────────────
    # Callback router & error handlers
    # ──────────────────────────────────────

    async def _callback_router(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Route all callback queries by prefix in callback_data."""
        query: Optional[CallbackQuery] = update.callback_query
        if not query or not query.data:
            return

        data = query.data
        try:
            if data.startswith("delkey:"):
                await self._cb_delete_key(query)
            elif data.startswith("msgdone:"):
                await self._cb_mark_message_done(query)
            elif data.startswith("actok:"):
                await self._cb_activation_approve(query)
            elif data.startswith("actrej:"):
                await self._cb_activation_reject(query)
            else:
                await query.answer(
                    "Эта кнопка пока не активна. Откройте главное меню через «📱 Меню».",
                    show_alert=False,
                )
        except Exception as e:
            logger.error("Error handling callback '%s': %s", data, e, exc_info=True)
            try:
                await query.answer("Ошибка обработки на сервере.", show_alert=True)
            except Exception:
                pass

    async def _cb_delete_key(self, query: CallbackQuery) -> None:
        """Handle inline delete of a VPN key."""
        await query.answer()
        data = query.data or ""
        try:
            key_id = int(data.split(":", 1)[1])
        except (IndexError, ValueError):
            return

        # Get key and user before deletion
        with get_db_session() as session:
            vpn_key = session.query(VPNKey).filter(VPNKey.id == key_id).first()
            if not vpn_key:
                await query.edit_message_text("Ключ не найден.")
                return
            user = vpn_key.user

        # Delete via VPNManager (also updates DB / files)
        success = await self.vpn_manager.delete_key(key_id)
        if not success:
            await query.edit_message_text(
                "Не удалось удалить ключ. Попробуй позже или обратись к админу."
            )
            return

        await query.edit_message_text(
            f"Ключ '{vpn_key.key_name}' удалён.",
        )

        # Отправим обновлённый список отдельным сообщением
        if query.message:
            await self._handle_list_keys(user, query.message)

    async def _cb_mark_message_done(self, query: CallbackQuery) -> None:
        """Mark a user message as resolved in the database."""
        await query.answer()
        data = query.data or ""
        try:
            msg_id = int(data.split(":", 1)[1])
        except (IndexError, ValueError):
            return

        with get_db_session() as session:
            msg = session.query(UserMessage).filter(UserMessage.id == msg_id).first()
            if not msg:
                await query.edit_message_text("Сообщение не найдено.")
                return
            msg.status = "resolved"
            msg.replied_at = datetime.utcnow()

        # Remove inline buttons but keep the text
        if query.message:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                # Fallback: just send info message
                await query.message.reply_text("Сообщение помечено как обработанное.")

    async def _cb_activation_approve(self, query: CallbackQuery) -> None:
        """Approve an account activation request and set max_keys."""
        await query.answer()
        data = query.data or ""
        try:
            _, msg_id_str, keys_str = data.split(":", 2)
            msg_id = int(msg_id_str)
            max_keys = int(keys_str)
        except (ValueError, IndexError):
            return

        if max_keys <= 0:
            max_keys = 1

        with get_db_session() as session:
            msg = session.query(UserMessage).filter(UserMessage.id == msg_id).first()
            if not msg:
                if query.message:
                    await query.edit_message_text("Запрос активации не найден.")
                return

            user = session.query(User).filter(User.id == msg.user_id).first()
            if not user:
                if query.message:
                    await query.edit_message_text("Пользователь для этого запроса не найден.")
                return

            user.is_active = True
            user.max_keys = max_keys
            user.activation_requested = False
            msg.status = "approved"
            msg.replied_at = datetime.utcnow()

        user_label = (
            user.nickname
            or user.username
            or f"{user.first_name or ''} {user.last_name or ''}".strip()
            or f"user#{user.id}"
        )

        # Update admin message UI
        if query.message:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            await query.message.reply_text(
                f"✅ Аккаунт пользователя {user_label} активирован, "
                f"выдано ключей: {max_keys}.",
                reply_markup=build_admin_keyboard(),
            )

        # Notify user about activation
        if user.telegram_id:
            try:
                await self.application.bot.send_message(
                    chat_id=user.telegram_id,
                    text=(
                        "✅ Твой аккаунт в MOROZ VPN активирован.\n\n"
                        f"Тебе доступно ключей: {max_keys}.\n"
                        "Открой «📱 Меню», чтобы получить ключ."
                    ),
                    reply_markup=build_main_keyboard(),
                )
            except Exception as e:
                logger.warning(
                    "Failed to notify user %s about activation: %s",
                    user.telegram_id,
                    e,
                )

    async def _cb_activation_reject(self, query: CallbackQuery) -> None:
        """Reject an account activation request."""
        await query.answer()
        data = query.data or ""
        try:
            msg_id = int(data.split(":", 1)[1])
        except (ValueError, IndexError):
            return

        with get_db_session() as session:
            msg = session.query(UserMessage).filter(UserMessage.id == msg_id).first()
            if not msg:
                if query.message:
                    await query.edit_message_text("Запрос активации не найден.")
                return

            user = session.query(User).filter(User.id == msg.user_id).first()
            if not user:
                if query.message:
                    await query.edit_message_text("Пользователь для этого запроса не найден.")
                return

            msg.status = "rejected"
            msg.replied_at = datetime.utcnow()
            user.activation_requested = False

        user_label = (
            user.nickname
            or user.username
            or f"{user.first_name or ''} {user.last_name or ''}".strip()
            or f"user#{user.id}"
        )

        # Update admin message UI
        if query.message:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            await query.message.reply_text(
                f"❌ Запрос активации пользователя {user_label} отклонён.",
                reply_markup=build_admin_keyboard(),
            )

        # Notify user about rejection
        if user.telegram_id:
            try:
                await self.application.bot.send_message(
                    chat_id=user.telegram_id,
                    text=(
                        "К сожалению, запрос на активацию аккаунта отклонён.\n\n"
                        "Если считаешь, что это ошибка, свяжись с администратором."
                    ),
                    reply_markup=build_inactive_user_keyboard(),
                )
            except Exception as e:
                logger.warning(
                    "Failed to notify user %s about activation rejection: %s",
                    user.telegram_id,
                    e,
                )

    async def _notify_admin_activation_request(
        self,
        user: User,
        msg_id: int,
    ) -> None:
        """Notify admin about an account activation request with inline controls."""
        admin_id = get_admin_id()
        if not admin_id:
            return

        user_label = (
            user.nickname
            or user.username
            or f"{user.first_name or ''} {user.last_name or ''}".strip()
            or f"user#{user.id}"
        )

        lines = [
            "🔓 Запрос активации аккаунта",
            "",
            f"Пользователь: {user_label}",
            f"Telegram ID: {user.telegram_id}",
            f"ID в БД: {user.id}",
            f"Телефон: {user.phone_number or '—'}",
            "",
            "Выбери, сколько ключей выдать при активации, "
            "или отклони запрос.",
        ]

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="✅ Одобрить (1 ключ)",
                        callback_data=f"actok:{msg_id}:1",
                    ),
                    InlineKeyboardButton(
                        text="✅ Одобрить (2 ключа)",
                        callback_data=f"actok:{msg_id}:2",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="✅ Одобрить (3 ключа)",
                        callback_data=f"actok:{msg_id}:3",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отклонить",
                        callback_data=f"actrej:{msg_id}",
                    ),
                ],
            ]
        )

        try:
            await self.application.bot.send_message(
                chat_id=admin_id,
                text="\n".join(lines),
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.warning(
                "Failed to notify admin about activation request msg_id=%s: %s",
                msg_id,
                e,
            )

    async def _notify_admin_new_message(
        self,
        user: User,
        message_type: str,
        message_text: str,
        msg_id: int,
    ) -> None:
        """Send a brief notification about a new user message to the admin."""
        admin_id = get_admin_id()
        if not admin_id or admin_id == (user.telegram_id or 0):
            return

        type_emoji = {
            "question": "❓ Вопрос",
            "problem": "🐛 Проблема",
            "key_request": "🔑 Запрос ключа",
            "activation": "🔓 Запрос активации",
        }.get(message_type, "📨 Сообщение")

        user_label = (
            user.nickname
            or user.username
            or f"{user.first_name or ''} {user.last_name or ''}".strip()
            or f"user#{user.id}"
        )

        lines = [
            "📨 Новое сообщение от пользователя",
            f"Тип: {type_emoji}",
            f"Пользователь: {user_label}",
            f"Telegram ID: {user.telegram_id}",
            f"ID в БД: {user.id}",
            "",
            f"Текст:",
            message_text,
        ]

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="✅ Отметить обработанным",
                        callback_data=f"msgdone:{msg_id}",
                    )
                ]
            ]
        )

        try:
            await self.application.bot.send_message(
                chat_id=admin_id,
                text="\n".join(lines),
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.warning("Failed to notify admin about message %s: %s", msg_id, e)

    async def _application_error_handler(
        self,
        update: object,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """
        Global error handler for the Application.

        Implements the behaviour described in the TZ:
        - logs all unexpected errors
        - handles outdated callbacks gracefully
        - warns about polling conflicts
        - adds small delays on network issues
        """
        from telegram.error import BadRequest, Conflict, TimedOut, NetworkError

        err = context.error
        logger.error("Unhandled error in update %s: %s", update, err, exc_info=True)

        # Outdated callbacks and similar harmless issues
        if isinstance(err, BadRequest) and (
            "query is too old" in str(err).lower()
            or "message is not modified" in str(err).lower()
        ):
            return

        # Multiple instances of the bot running
        if isinstance(err, Conflict):
            logger.error(
                "Telegram Conflict error: another instance of the bot is running."
            )
            await asyncio.sleep(5)
            return

        # Transient network issues
        if isinstance(err, (TimedOut, NetworkError)):
            await asyncio.sleep(3)

    # ──────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────

    def run(self) -> None:
        """Start polling using the built-in run_polling helper."""
        logger.info("Starting VPNBot polling…")
        self.application.run_polling()


def main() -> None:
    bot = VPNBot()
    bot.run()


if __name__ == "__main__":
    main()

