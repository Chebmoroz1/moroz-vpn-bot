"""Telegram бот для управления VPN"""
import asyncio
import logging
import re
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.error import BadRequest, TimedOut, NetworkError, Conflict

from config import BOT_TOKEN, ADMIN_ID, VPN_CONFIGS_DIR, WEB_SERVER_URL
from ml_cloud_payment_flow import get_payment_flow
from database import init_db, get_db_session, User, VPNKey, Payment
from sqlalchemy import func
from contacts import contacts_manager
from vpn_manager import vpn_manager
from config_manager import config_manager
from price_calculator import price_calculator
import requests

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class VPNBot:
    """Основной класс бота"""

    def __init__(self):
        self.app = None
        self._stale_query_hint = (
            "⚠️ Эта кнопка устарела. Откройте меню заново через '📱 Меню' или команду /start."
        )

    def _is_stale_query_error(self, error: Exception) -> bool:
        """Проверка, что ошибка связана с устаревшим callback-запросом"""
        message = str(error).lower()
        stale_fragments = (
            "query is too old",
            "response timeout expired",
            "query id is invalid",
            "timeout expired"
        )
        return any(fragment in message for fragment in stale_fragments)

    async def _inform_stale_query(self, query):
        """Отправляет пользователю подсказку о том, что кнопка устарела"""
        try:
            reply_keyboard = self._get_reply_keyboard()
            if query and query.message:
                await query.message.reply_text(self._stale_query_hint, reply_markup=reply_keyboard)
        except Exception as notify_error:
            logger.warning(f"Failed to notify about stale query: {notify_error}")

    async def _safe_answer_callback(self, query) -> bool:
        """
        Безопасно отвечает на callback-запрос. Возвращает False, если запрос устарел
        и дальнейшая обработка не требуется.
        """
        if not query:
            return False
        try:
            await query.answer()
            return True
        except BadRequest as e:
            if self._is_stale_query_error(e):
                await self._inform_stale_query(query)
                return False
            raise

    async def _safe_edit_message_text(self, query, *, text: str, **kwargs):
        """
        Обертка над edit_message_text, которая перехватывает типовые ошибки Telegram
        и старается не обрывать сценарий для пользователя.
        """
        if not query:
            return
        try:
            await query.edit_message_text(text=text, **kwargs)
        except BadRequest as e:
            lower_msg = str(e).lower()
            if "message is not modified" in lower_msg:
                logger.debug("Skipping edit_message_text: message not modified")
                if query.message:
                    await query.message.reply_text(text, **kwargs)
                return
            if self._is_stale_query_error(e):
                await self._inform_stale_query(query)
                return
            raise

    async def _application_error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Глобальный обработчик ошибок Application"""
        error = context.error
        logger.error("Unhandled error while processing update: %s", error, exc_info=True)

        if isinstance(error, BadRequest) and self._is_stale_query_error(error):
            # Ошибка уже обработана локально, повторно игнорируем
            return

        if isinstance(error, Conflict):
            logger.warning("Telegram reported polling conflict. Ensure only one bot instance is running.")

        if isinstance(error, (TimedOut, NetworkError)):
            # Небольшая пауза, чтобы не спамить лог при временных сетевых проблемах
            await asyncio.sleep(1)
    
    async def _make_http_request_with_retry(self, method: str, url: str, **kwargs):
        """
        Выполнение HTTP запроса с автоматическим retry
        :param method: HTTP метод (GET, POST, etc.)
        :param url: URL для запроса
        :param kwargs: Дополнительные параметры для requests
        :return: Response объект
        """
        loop = asyncio.get_event_loop()
        
        # Синхронная функция для retry
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=0.5, max=5),
            retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout)),
            reraise=True
        )
        def _sync_request():
            return getattr(requests, method.lower())(url, **kwargs)
        
        # Выполняем запрос в отдельном потоке, чтобы не блокировать event loop
        return await loop.run_in_executor(None, _sync_request)
    
    def _get_user_display_name(self, user: User) -> str:
        """Получить отображаемое имя пользователя (nickname, если есть, иначе username или имя)"""
        if user.nickname:
            return user.nickname
        if user.username:
            return f"@{user.username}"
        if user.first_name:
            return user.first_name
        return f"User #{user.id}"
    
    def _get_user_display_name_with_username(self, user: User) -> str:
        """Получить отображаемое имя пользователя с username в скобках (если есть nickname)"""
        display_name = self._get_user_display_name(user)
        # Если используется nickname, добавляем username в скобках, если он есть
        if user.nickname and user.username:
            return f"{user.nickname} (@{user.username})"
        return display_name
    
    def _format_user_button_name(self, display_name: str, keys_count: int, max_keys: int, max_length: int = 50) -> str:
        """
        Форматирует имя пользователя для кнопки с информацией о ключах
        Умно обрезает длинные имена, сохраняя информацию о ключах видимой
        
        :param display_name: Отображаемое имя пользователя (может включать статус и иконки)
        :param keys_count: Количество выданных ключей
        :param max_keys: Максимальное количество ключей
        :param max_length: Максимальная длина кнопки (по умолчанию 50)
        :return: Отформатированная строка для кнопки в формате "👤 ✅ 👑 Имя (X/Y)"
        """
        # Префикс и суффикс
        prefix = "👤 "
        keys_info = f" ({keys_count}/{max_keys})"
        
        # Вычисляем доступную длину для имени
        # Учитываем, что keys_info может быть разной длины (например, " (1/1)" vs " (10/100)")
        reserved_length = len(prefix) + len(keys_info)
        available_length = max_length - reserved_length
        
        # Минимальная длина для имени (чтобы было хоть что-то видно)
        min_name_length = 5
        
        # Обрезаем имя, если оно слишком длинное
        if len(display_name) > available_length:
            # Обрезаем с учетом многоточия
            # Оставляем место для "..." (3 символа)
            truncate_to = max(min_name_length, available_length - 3)
            truncated_name = display_name[:truncate_to] + "..."
            return f"{prefix}{truncated_name}{keys_info}"
        else:
            return f"{prefix}{display_name}{keys_info}"

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        chat = update.effective_chat

        logger.info(f"=== START COMMAND RECEIVED ===")
        logger.info(f"User {user.id} (@{user.username}) started bot")

        # Проверка авторизации по БД
        db = get_db_session()
        try:
            # Ищем пользователя в БД по Telegram ID
            db_user = db.query(User).filter(User.telegram_id == user.id).first()

            # Если пользователь не найден, проверяем по телефону (для миграции из contacts.json)
            if not db_user:
                # Ищем в БД по телефону через contacts_manager для нормализации
                # Но основная логика теперь работает через БД
                await self._request_phone_number(update, context)
                return

            # Обновляем данные пользователя
            db_user.username = user.username
            db_user.first_name = user.first_name
            db_user.last_name = user.last_name
            db_user.is_admin = (user.id == ADMIN_ID)
            db.commit()

            # Проверяем активность
            if not db_user.is_active:
                # Показываем меню для неактивных пользователей
                await self._show_inactive_user_menu(update, context, db_user)
                return

            # Показываем главное меню (постоянная клавиатура показывается внутри функции)
            await self._show_main_menu(update, context, db_user)

        except Exception as e:
            logger.error(f"Error in start_command: {e}")
            await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")
        finally:
            db.close()

    async def _request_phone_number(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запрос номера телефона или показ меню для неактивных пользователей"""
        user = update.effective_user
        
        # Создаем нового пользователя как неактивного
        db = get_db_session()
        try:
            # Проверяем, не создан ли уже пользователь
            db_user = db.query(User).filter(User.telegram_id == user.id).first()
            
            if not db_user:
                # Создаем нового пользователя (неактивного)
                new_user = User(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name or "Неавторизованный",
                    last_name=user.last_name,
                    is_active=False,  # Неактивный по умолчанию
                    is_admin=(user.id == ADMIN_ID),
                    max_keys=0,  # Нет доступа до активации
                    activation_requested=False,
                    activation_requested_at=None
                )
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                db_user = new_user
                logger.info(f"New user created: ID={new_user.id}, telegram_id={user.id}")
            
            # Показываем меню для неактивных пользователей (постоянная клавиатура показывается внутри функции)
            await self._show_inactive_user_menu(update, context, db_user)
        finally:
            db.close()

    async def handle_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик контакта (номера телефона)"""
        user = update.effective_user
        contact = update.message.contact

        logger.info(f"User {user.id} sent contact: {contact.phone_number}")

        # Нормализуем номер телефона сразу при получении
        raw_phone = contact.phone_number
        phone = contacts_manager._normalize_phone(raw_phone)
        logger.info(f"Checking authorization for phone: {raw_phone} (raw from Telegram) -> {phone} (normalized)")
        
        # Проверяем авторизацию по БД (ищем пользователя по телефону)
        db = get_db_session()
        try:
            # Ищем пользователя по телефону в БД
            user_by_phone = db.query(User).filter(User.phone_number == phone).first()
            
            # Ищем пользователя по Telegram ID
            user_by_telegram = db.query(User).filter(User.telegram_id == user.id).first()
            
            # Обрабатываем различные сценарии
            if user_by_phone and user_by_telegram:
                # Оба пользователя существуют - объединяем их
                if user_by_phone.id != user_by_telegram.id:
                    logger.info(f"Found both users: by phone (ID={user_by_phone.id}) and by telegram (ID={user_by_telegram.id}), merging...")
                    # Обновляем пользователя с telegram_id, добавляя телефон, если его нет
                    if not user_by_telegram.phone_number:
                        user_by_telegram.phone_number = phone
                    # Копируем другие данные, если они отсутствуют
                    if not user_by_telegram.first_name and user_by_phone.first_name:
                        user_by_telegram.first_name = user_by_phone.first_name
                    if not user_by_telegram.last_name and user_by_phone.last_name:
                        user_by_telegram.last_name = user_by_phone.last_name
                    if not user_by_telegram.nickname and user_by_phone.nickname:
                        user_by_telegram.nickname = user_by_phone.nickname
                    # Используем более высокий max_keys
                    if user_by_phone.max_keys > user_by_telegram.max_keys:
                        user_by_telegram.max_keys = user_by_phone.max_keys
                    # Используем статус активности из пользователя с телефоном, если он активен
                    if user_by_phone.is_active and not user_by_telegram.is_active:
                        user_by_telegram.is_active = True
                    db.commit()
                    # Удаляем дубликат (пользователя, найденного по телефону)
                    db.delete(user_by_phone)
                    db.commit()
                    db_user = user_by_telegram
                    logger.info(f"Users merged, using user ID={db_user.id}")
                else:
                    # Это один и тот же пользователь
                    db_user = user_by_phone
            elif user_by_phone:
                # Найден только по телефону
                db_user = user_by_phone
                # Проверяем, нет ли другого пользователя с таким telegram_id
                existing_with_telegram = db.query(User).filter(User.telegram_id == user.id).first()
                if existing_with_telegram:
                    # Есть другой пользователь с таким telegram_id - объединяем
                    logger.info(f"Found user by phone (ID={db_user.id}), but another user exists with telegram_id (ID={existing_with_telegram.id}), merging...")
                    # Обновляем существующего пользователя с telegram_id
                    if not existing_with_telegram.phone_number:
                        existing_with_telegram.phone_number = phone
                    if not existing_with_telegram.first_name and db_user.first_name:
                        existing_with_telegram.first_name = db_user.first_name
                    if not existing_with_telegram.last_name and db_user.last_name:
                        existing_with_telegram.last_name = db_user.last_name
                    if not existing_with_telegram.nickname and db_user.nickname:
                        existing_with_telegram.nickname = db_user.nickname
                    if db_user.max_keys > existing_with_telegram.max_keys:
                        existing_with_telegram.max_keys = db_user.max_keys
                    if db_user.is_active and not existing_with_telegram.is_active:
                        existing_with_telegram.is_active = True
                    db.commit()
                    # Удаляем дубликат
                    db.delete(db_user)
                    db.commit()
                    db_user = existing_with_telegram
                else:
                    # Обновляем telegram_id
                    if not db_user.telegram_id:
                        logger.info(f"Found user by phone, updating telegram_id: ID={db_user.id}, phone={phone}, telegram_id={user.id}")
                        db_user.telegram_id = user.id
                        db.commit()
            elif user_by_telegram:
                # Найден только по Telegram ID
                db_user = user_by_telegram
                # Обновляем телефон, если его нет
                if not db_user.phone_number:
                    logger.info(f"Found user by telegram_id, updating phone: ID={db_user.id}, telegram_id={user.id}, phone={phone}")
                    db_user.phone_number = phone
                    db.commit()
            else:
                # Пользователь не найден
                db_user = None
            
            # Если пользователь не найден, создаем нового пользователя
            if not db_user:
                logger.info(f"User not found in database, creating new user for phone: {phone}, telegram_id: {user.id}")
                
                # Создаем нового пользователя (неактивного, чтобы он мог запросить активацию)
                new_user = User(
                    telegram_id=user.id,
                    phone_number=phone,
                    username=user.username,
                    first_name=user.first_name or "Неавторизованный",
                    last_name=user.last_name,
                    is_active=False,  # Неактивный по умолчанию
                    is_admin=(user.id == ADMIN_ID),
                    max_keys=1,
                    activation_requested=False,  # Новый пользователь - может запросить активацию
                    activation_requested_at=None
                )
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                db_user = new_user
                
                logger.info(f"New user created: ID={new_user.id}, phone={phone}, telegram_id={user.id}")
                
                # Показываем меню для неактивных пользователей
                await update.message.reply_text(
                    "✅ Данные обновлены!",
                    reply_markup=InlineKeyboardMarkup([[]])
                )
                await self._show_inactive_user_menu(update, context, db_user)
                return
            
            # Обновляем данные пользователя в БД (только если изменились)
            updated = False
            if db_user.telegram_id != user.id:
                db_user.telegram_id = user.id
                updated = True
            if db_user.phone_number != phone:
                db_user.phone_number = phone
                updated = True
            if db_user.username != user.username:
                db_user.username = user.username
                updated = True
            if db_user.first_name != user.first_name:
                db_user.first_name = user.first_name
                updated = True
            if db_user.last_name != user.last_name:
                db_user.last_name = user.last_name
                updated = True
            if db_user.is_admin != (user.id == ADMIN_ID):
                db_user.is_admin = (user.id == ADMIN_ID)
                updated = True
            
            if updated:
                db.commit()
            
            # Проверяем активность
            if not db_user.is_active:
                # Убираем клавиатуру с номером телефона
                await update.message.reply_text(
                    "✅ Данные обновлены!",
                    reply_markup=InlineKeyboardMarkup([[]])
                )
                # Показываем меню для неактивных пользователей
                await self._show_inactive_user_menu(update, context, db_user)
                return

            # Убираем клавиатуру с номером телефона
            await update.message.reply_text(
                "✅ Авторизация успешна!",
                reply_markup=InlineKeyboardMarkup([[]])
            )

            # Показываем главное меню
            await self._show_main_menu(update, context, db_user)

        except Exception as e:
            logger.error(f"Error handling contact: {e}", exc_info=True)
            try:
                await update.message.reply_text("❌ Произошла ошибка при авторизации. Попробуйте позже или обратитесь к администратору.")
            except Exception as send_error:
                logger.error(f"Error sending error message: {send_error}")
        finally:
            try:
                db.close()
            except Exception as close_error:
                logger.error(f"Error closing database: {close_error}")

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений (для добавления пользователей)"""
        user = update.effective_user
        text_msg = update.message.text
        
        # Проверяем, не является ли это командой (на всякий случай)
        if text_msg and text_msg.startswith('/'):
            logger.warning(f"handle_text_message received command: '{text_msg}' - this should not happen!")
            return
        
        logger.info(f"handle_text_message called for user {user.id} with text: '{text_msg}'")
        logger.info(f"context.user_data keys: {list(context.user_data.keys())}")
        logger.info(f"admin_adding_user flag: {context.user_data.get('admin_adding_user', False)}")

        db = get_db_session()
        try:
            db_user = db.query(User).filter(User.telegram_id == user.id).first()
            
            logger.info(f"db_user found: {db_user is not None}")
            if db_user:
                logger.info(f"db_user.is_admin: {db_user.is_admin}")
            
            # Обработка кнопки "Меню"
            if text_msg == "📱 Меню" or text_msg == "Меню":
                db.close()
                if not db_user:
                    # Если пользователь не найден, создаем его
                    await self._request_phone_number(update, context)
                    return
                elif not db_user.is_active:
                    # Показываем меню для неактивных пользователей
                    await self._show_inactive_user_menu(update, context, db_user)
                    return
                else:
                    # Показываем главное меню
                    await self._show_main_menu(update, context, db_user)
                    return
            
            # Проверяем, является ли пользователь администратором и находится ли в режиме добавления пользователя
            if db_user and db_user.is_admin and context.user_data.get('admin_adding_user'):
                logger.info(f"Processing admin add user text: '{text_msg}'")
                # Закрываем текущую сессию перед обработкой
                db.close()
                await self._handle_admin_add_user_text(update, context, db_user, text_msg)
                return
            
            # Проверяем, редактируется ли настройка
            if db_user and db_user.is_admin and context.user_data.get('admin_editing_setting'):
                setting_key = context.user_data.get('admin_editing_setting')
                logger.info(f"Processing admin edit setting text: '{text_msg}' for key: {setting_key}")
                db.close()
                await self._handle_admin_setting_edit_text(update, context, db_user, setting_key, text_msg)
                return
            
            # Проверяем, ожидается ли ввод суммы доната
            if context.user_data.get('waiting_for_donation_amount'):
                db.close()
                await self._handle_donation_amount_input(update, context, db_user, text_msg)
                return
            
            # Проверяем, добавляется ли настройка
            if db_user and db_user.is_admin and context.user_data.get('admin_adding_setting'):
                category = context.user_data.get('admin_adding_setting')
                setting_key = context.user_data.get('admin_adding_setting_key')
                
                if setting_key:
                    # Добавление настройки из шаблона или вручную
                    logger.info(f"Processing admin add setting text: '{text_msg}' for key: {setting_key}")
                    db.close()
                    desc = context.user_data.get('admin_adding_setting_desc', 'Настройка приложения')
                    is_secret = context.user_data.get('admin_adding_setting_secret', False)
                    await self._handle_admin_setting_add_text(update, context, db_user, category, setting_key, text_msg, desc, is_secret)
                    return
                else:
                    # Добавление настройки вручную (формат: ключ=значение)
                    if '=' in text_msg:
                        parts = text_msg.split('=', 1)
                        key = parts[0].strip()
                        value = parts[1].strip()
                        logger.info(f"Processing admin add setting manually: key='{key}'")
                        db.close()
                        await self._handle_admin_setting_add_text(update, context, db_user, category, key, value, 'Настройка приложения', False)
                        return
                    else:
                        # Только ключ, просим значение
                        await update.message.reply_text(
                            f"Ключ: `{text_msg}`\n\nОтправьте значение для этой настройки:",
                            parse_mode='Markdown'
                        )
                        context.user_data['admin_adding_setting_key'] = text_msg
                        return
            else:
                logger.info(f"Ignoring text message: db_user={db_user is not None}, is_admin={db_user.is_admin if db_user else False}, admin_adding_user={context.user_data.get('admin_adding_user', False)}")
            # Иначе игнорируем текст (не команды не обрабатываются)

        except Exception as e:
            logger.error(f"Error handling text message: {e}", exc_info=True)
        finally:
            if db:
                db.close()

    async def _handle_admin_add_user_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User, text_input: str):
        """Обработка текстового ввода для добавления пользователя"""
        text_input = text_input.strip()
        logger.info(f"Admin adding user with input: '{text_input}'")

        # Определяем, что это - номер телефона или Telegram ID
        is_phone = False
        is_telegram_id = False
        telegram_id = None

        # Сначала проверяем, является ли номером телефона (российский номер начинается с 7, 8 или +7)
        # Проверяем формат номера телефона ПЕРЕД проверкой Telegram ID
        clean_text = ''.join(c for c in text_input if c.isdigit() or c == '+')
        digit_count = sum(1 for c in clean_text if c.isdigit())
        
        # Номер телефона должен иметь от 10 до 12 цифр и начинаться с 7, 8 или +
        if (digit_count >= 10 and digit_count <= 12) and (
            clean_text.startswith('7') or 
            clean_text.startswith('8') or 
            clean_text.startswith('+7') or
            clean_text.startswith('+8')
        ):
            is_phone = True
            logger.info(f"Detected as phone number: '{text_input}' (digits: {digit_count})")
        
        # Если не номер телефона, проверяем, является ли Telegram ID
        if not is_phone:
            try:
                telegram_id = int(text_input)
                if telegram_id > 1000000:  # Telegram ID обычно больше 1000000
                    is_telegram_id = True
                    logger.info(f"Detected as Telegram ID: {telegram_id}")
            except ValueError:
                pass


        db = get_db_session()
        try:
            if is_phone:
                # Нормализуем номер телефона
                normalized = contacts_manager._normalize_phone(text_input)
                logger.info(f"Adding phone number to database: '{text_input}' -> '{normalized}'")
                
                # Проверяем, существует ли пользователь с таким номером
                existing_user = db.query(User).filter(User.phone_number == normalized).first()
                
                if existing_user:
                    # Если пользователь существует, но был удален - восстанавливаем
                    if existing_user.is_deleted:
                        existing_user.is_deleted = False
                        existing_user.is_active = True
                        db.commit()
                        result_msg = f"✅ Пользователь с номером {normalized} восстановлен"
                    else:
                        result_msg = f"✅ Пользователь с номером {normalized} уже существует"
                else:
                    # Создаем нового пользователя в БД
                    new_user = User(
                        phone_number=normalized,
                        first_name="Неавторизованный",
                        max_keys=1,
                        is_active=True,
                        is_deleted=False
                    )
                    db.add(new_user)
                    db.commit()
                    result_msg = f"✅ Пользователь с номером {normalized} создан в базе данных"
                    logger.info(f"User created with phone: {normalized}, ID: {new_user.id}")
                    
            elif is_telegram_id:
                # Создаем или обновляем пользователя в БД по Telegram ID
                existing_user = db.query(User).filter(User.telegram_id == telegram_id).first()
                
                if existing_user:
                    # Если пользователь существует, но был удален - восстанавливаем
                    if existing_user.is_deleted:
                        existing_user.is_deleted = False
                        existing_user.is_active = True
                        db.commit()
                        result_msg = f"✅ Пользователь с Telegram ID {telegram_id} восстановлен"
                    else:
                        result_msg = f"✅ Пользователь с Telegram ID {telegram_id} уже существует"
                else:
                    # Создаем нового пользователя
                    new_user = User(
                        telegram_id=telegram_id,
                        first_name="Неавторизованный",
                        max_keys=1,
                        is_active=True,
                        is_deleted=False
                    )
                    db.add(new_user)
                    db.commit()
                    result_msg = f"✅ Пользователь с Telegram ID {telegram_id} создан в базе данных"
                    logger.info(f"User created with telegram_id: {telegram_id}, ID: {new_user.id}")
            else:
                await update.message.reply_text(
                    "❌ Неверный формат. Отправьте:\n"
                    "• Номер телефона: +79001234567\n"
                    "• Или Telegram ID: 123456789"
                )
                return

            # Сбрасываем флаг добавления пользователя
            context.user_data.pop('admin_adding_user', None)
            
            # Показываем сообщение об успехе и возвращаемся в админ-панель
            keyboard = [
                [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
                [InlineKeyboardButton("◀️ В админ-панель", callback_data="admin_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                result_msg,
                reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error adding user: {e}", exc_info=True)
            await update.message.reply_text("❌ Произошла ошибка при добавлении пользователя.")
        finally:
            db.close()

    def _get_reply_keyboard(self):
        """Получить постоянную клавиатуру с кнопкой меню"""
        keyboard = [
            [KeyboardButton("📱 Меню")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    async def _show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Показ главного меню"""
        # Используем nickname, если есть, иначе имя
        display_name = self._get_user_display_name(db_user)
        greeting = f"👋 Привет, {display_name}!"

        text = f"{greeting}\n\nВыберите действие:"

        keyboard = [
            [InlineKeyboardButton("🔐 Получить AmneziaWG ключ", callback_data="create_key")],
            [InlineKeyboardButton("💳 Оплатить VPN", callback_data="pay_vpn")],
            [InlineKeyboardButton("📋 Мои ключи", callback_data="my_keys")],
        ]

        if db_user.is_admin:
            keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])

        keyboard.append([InlineKeyboardButton("ℹ️ Помощь", callback_data="help")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        reply_keyboard = self._get_reply_keyboard()

        if update.callback_query:
            await self._safe_edit_message_text(update.callback_query, text=text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text=text, reply_markup=reply_markup)
            # Показываем постоянную клавиатуру с кнопкой меню
            await update.message.reply_text(
                "Используйте кнопку ниже для быстрого доступа к меню:",
                reply_markup=reply_keyboard
            )

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов"""
        query = update.callback_query
        if not await self._safe_answer_callback(query):
            return

        data = query.data
        user_id = query.from_user.id

        # Обработка меню покупки для неавторизованных пользователей (до проверки db_user)
        if data == "purchase_menu":
            await self._show_purchase_menu(update, context)
            return
        elif data.startswith("purchase_months:"):
            action = data.split(":")[1]
            await self._handle_purchase_months(update, context, action)
            return
        elif data.startswith("purchase_codes:"):
            action = data.split(":")[1]
            await self._handle_purchase_codes(update, context, action)
            return
        elif data == "purchase_pay":
            await self._handle_purchase_pay(update, context)
            return
        elif data == "back_to_inactive_menu":
            # Получаем пользователя для показа меню неактивных
            db = get_db_session()
            try:
                db_user = db.query(User).filter(User.telegram_id == user_id).first()
                if db_user and not db_user.is_active:
                    await self._show_inactive_user_menu(update, context, db_user)
                else:
                    await self._show_purchase_menu(update, context)
            finally:
                db.close()
            return
        
        # Для остальных действий нужна авторизация
        db = get_db_session()
        try:
            db_user = db.query(User).filter(User.telegram_id == user_id).first()
            if not db_user:
                # Если пользователь не найден, показываем меню покупки
                await self._show_purchase_menu(update, context)
                return
            elif not db_user.is_active:
                # Если пользователь неактивен, обрабатываем специальные действия
                if data == "request_activation":
                    await self._handle_request_activation(update, context, db_user)
                    return
                elif data == "provide_phone":
                    await self._handle_provide_phone(update, context, db_user)
                    return
                elif data not in ["help", "purchase_menu", "request_activation", "provide_phone"]:
                    # Для других действий показываем меню неактивных пользователей
                    await self._show_inactive_user_menu(update, context, db_user)
                    return

            if data == "create_key":
                await self._handle_create_key(update, context, db_user)
            elif data == "pay_vpn":
                await self._show_donation_menu(update, context, db_user)
            elif data.startswith("donation_amount:"):
                amount = int(data.split(":")[1])
                await self._handle_donation_payment(update, context, db_user, amount)
            elif data == "donation_custom":
                await self._handle_custom_donation(update, context, db_user)
            elif data == "my_keys":
                await self._handle_my_keys(update, context, db_user)
            elif data.startswith("delete_key:"):
                # Получаем key_id из callback_data
                key_id = int(data.split(":")[1])
                await self._handle_delete_key(update, context, db_user, key_id)
            elif data == "check_payment_balance":
                await self._handle_check_payment_balance(update, context, db_user)
            elif data == "back_to_menu":
                await self._show_main_menu(update, context, db_user)
            elif data == "admin_panel":
                if db_user.is_admin:
                    await self._handle_admin_panel(update, context, db_user)
                else:
                    await query.message.reply_text("❌ У вас нет доступа к админ-панели.")
            elif data == "admin_web_panel":
                if db_user.is_admin:
                    await self._handle_admin_web_panel(update, context, db_user)
                else:
                    await query.message.reply_text("❌ У вас нет доступа к веб-панели.")
            elif data == "admin_back":
                # Возврат в админ-панель
                await self._handle_admin_panel(update, context, db_user)
            elif data == "admin_users":
                if db_user.is_admin:
                    await self._handle_admin_users(update, context, db_user)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data == "admin_all_keys":
                if db_user.is_admin:
                    await self._handle_admin_all_keys(update, context, db_user)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_all_keys_page:"):
                if db_user.is_admin:
                    page = int(data.split(":")[1])
                    await self._handle_admin_all_keys(update, context, db_user, page=page)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data == "admin_settings":
                if db_user.is_admin:
                    await self._handle_admin_settings(update, context, db_user)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_settings_category:"):
                if db_user.is_admin:
                    category = data.split(":")[1]
                    await self._handle_admin_settings_category(update, context, db_user, category)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_setting_edit:"):
                if db_user.is_admin:
                    setting_key = data.split(":")[1]
                    await self._handle_admin_setting_edit(update, context, db_user, setting_key)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_setting_delete:"):
                if db_user.is_admin:
                    setting_key = data.split(":")[1]
                    await self._handle_admin_setting_delete(update, context, db_user, setting_key)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_setting_add:"):
                if db_user.is_admin:
                    category = data.split(":")[1]
                    await self._handle_admin_setting_add(update, context, db_user, category)
            elif data.startswith("admin_set_activation_keys:"):
                if db_user.is_admin:
                    # Формат: admin_set_activation_keys:{user_id}:{change}
                    parts = data.split(":")
                    target_user_id = int(parts[1])
                    change = parts[2]
                    await self._handle_admin_set_activation_keys(update, context, db_user, target_user_id, change)
            elif data.startswith("admin_activate_user:"):
                if db_user.is_admin:
                    # Формат: admin_activate_user:{user_id}:{keys_count} или admin_activate_user:{user_id}
                    parts = data.split(":")
                    target_user_id = int(parts[1])
                    keys_count = int(parts[2]) if len(parts) > 2 else 1
                    await self._handle_admin_activate_user(update, context, db_user, target_user_id, keys_count)
            elif data.startswith("admin_reject_user:"):
                if db_user.is_admin:
                    target_user_id = int(data.split(":")[1])
                    await self._handle_admin_reject_user(update, context, db_user, target_user_id)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_setting_add_template:"):
                if db_user.is_admin:
                    # Формат: admin_setting_add_template:category:key
                    parts = data.split(":")
                    category = parts[1]
                    template_key = parts[2]
                    await self._handle_admin_setting_add_template(update, context, db_user, category, template_key)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data == "admin_stats":
                if db_user.is_admin:
                    await self._handle_admin_stats(update, context, db_user)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_user_page:"):
                if db_user.is_admin:
                    page = int(data.split(":")[1])
                    await self._handle_admin_users(update, context, db_user, page=page)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_user_detail:"):
                if db_user.is_admin:
                    user_id = int(data.split(":")[1])
                    await self._handle_admin_user_detail(update, context, db_user, user_id)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_set_limit:"):
                if db_user.is_admin:
                    # Формат: admin_set_limit:user_id:limit_value
                    parts = data.split(":")
                    user_id = int(parts[1])
                    limit = int(parts[2])
                    await self._handle_admin_set_limit(update, context, db_user, user_id, limit)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_delete_user:"):
                if db_user.is_admin:
                    user_id = int(data.split(":")[1])
                    await self._handle_admin_delete_user(update, context, db_user, user_id)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_set_activation_keys:"):
                if db_user.is_admin:
                    # Формат: admin_set_activation_keys:{user_id}:{change}
                    parts = data.split(":")
                    target_user_id = int(parts[1])
                    change = parts[2]
                    await self._handle_admin_set_activation_keys(update, context, db_user, target_user_id, change)
            elif data.startswith("admin_activate_user:"):
                if db_user.is_admin:
                    # Формат: admin_activate_user:{user_id}:{keys_count} или admin_activate_user:{user_id}
                    parts = data.split(":")
                    target_user_id = int(parts[1])
                    keys_count = int(parts[2]) if len(parts) > 2 else 1
                    await self._handle_admin_activate_user(update, context, db_user, target_user_id, keys_count)
            elif data.startswith("admin_reject_user:"):
                if db_user.is_admin:
                    target_user_id = int(data.split(":")[1])
                    await self._handle_admin_reject_user(update, context, db_user, target_user_id)
            elif data == "admin_add_user":
                if db_user.is_admin:
                    await self._handle_admin_add_user(update, context, db_user)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data.startswith("admin_delete_key:"):
                if db_user.is_admin:
                    key_id = int(data.split(":")[1])
                    await self._handle_admin_delete_key(update, context, db_user, key_id)
                else:
                    await query.answer("❌ У вас нет доступа.", show_alert=True)
            elif data == "help":
                await self._handle_help(update, context)
            elif data == "noop":
                # Пустой callback для кнопок-индикаторов (не выполняют действий)
                await query.answer()

        except Exception as e:
            logger.error(f"Error in callback_handler: {e}")
            reply_keyboard = self._get_reply_keyboard()
            await query.message.reply_text("❌ Произошла ошибка. Попробуйте позже.", reply_markup=reply_keyboard)
        finally:
            db.close()

    async def _handle_create_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Создание VPN ключа"""
        query = update.callback_query

        db = get_db_session()
        try:
            # Проверяем, является ли пользователь платным (имеет успешные платежи) или бесплатным (активирован администратором)
            # Ищем успешные платежи типа qr_subscription
            successful_payments = db.query(Payment).filter(
                Payment.user_id == db_user.id,
                Payment.status == 'success',
                Payment.payment_type == 'qr_subscription'
            ).all()
            
            # Подсчитываем доступные QR-коды из успешных платежей
            total_available_codes = 0
            for payment in successful_payments:
                # Подсчитываем, сколько ключей уже создано из этого платежа
                keys_from_payment = db.query(VPNKey).filter(
                    VPNKey.payment_id == payment.id,
                    VPNKey.is_active == True
                ).count()
                # Доступные коды = купленные минус созданные
                available = payment.qr_code_count - keys_from_payment
                total_available_codes += max(0, available)
            
            # Проверяем, есть ли у пользователя бесплатный доступ (активирован администратором)
            is_free_user = db_user.is_active and db_user.max_keys > 0
            
            # Если есть успешные платежи - это платный пользователь
            is_paid_user = len(successful_payments) > 0
            
            if is_paid_user:
                # ПЛАТНЫЙ ПОЛЬЗОВАТЕЛЬ - проверяем доступные коды из платежей
                if total_available_codes <= 0:
                    await query.answer("❌ У вас нет доступных QR-кодов.", show_alert=True)
                    # Показываем пояснение и меню покупки
                    explanation_text = (
                        "❌ Достигнут лимит ключей.\n\n"
                        "Все купленные QR-коды уже использованы для создания ключей.\n"
                        "Для создания дополнительных ключей необходимо приобрести новые QR-коды.\n\n"
                        "Выберите количество кодов и период подписки:"
                    )
                    await self._safe_edit_message_text(query, text=explanation_text)
                    # Показываем меню покупки
                    await self._show_purchase_menu(update, context)
                    return
                
                # Находим платеж с доступными кодами
                payment_with_codes = None
                for payment in successful_payments:
                    keys_from_payment = db.query(VPNKey).filter(
                        VPNKey.payment_id == payment.id,
                        VPNKey.is_active == True
                    ).count()
                    if payment.qr_code_count - keys_from_payment > 0:
                        payment_with_codes = payment
                        break
                
                if not payment_with_codes:
                    await query.message.reply_text(
                        "❌ Не удалось найти доступный платеж для создания ключа."
                    )
                    return
                
            elif is_free_user:
                # БЕСПЛАТНЫЙ ПОЛЬЗОВАТЕЛЬ - проверяем лимит ключей
                # Подсчитываем только бесплатные ключи (access_type='free' или None)
                active_keys_count = db.query(VPNKey).filter(
                    VPNKey.user_id == db_user.id,
                    VPNKey.is_active == True
                ).filter(
                    (VPNKey.access_type == 'free') | (VPNKey.access_type.is_(None))
                ).count()
                
                if active_keys_count >= db_user.max_keys:
                    await query.answer(f"❌ Достигнут лимит ключей ({db_user.max_keys}).", show_alert=True)
                    # Предлагаем докупить еще ключей
                    text = (
                        f"❌ Достигнут лимит бесплатных ключей ({db_user.max_keys}/{db_user.max_keys}).\n\n"
                        "Вы использовали все доступные бесплатные ключи.\n"
                        "Для создания дополнительных ключей необходимо приобрести QR-коды.\n\n"
                        "Вы можете:\n"
                        "• 💳 Докупить дополнительные QR-коды (платно)\n"
                        "• 🗑 Удалить один из существующих ключей и создать новый бесплатно"
                    )
                    keyboard = [
                        [InlineKeyboardButton("💳 Докупить QR-коды", callback_data="purchase_menu")],
                        [InlineKeyboardButton("📋 Мои ключи", callback_data="my_keys")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)
                    return
                payment_with_codes = None
            else:
                # Пользователь не имеет ни платного, ни бесплатного доступа
                reply_keyboard = self._get_reply_keyboard()
                await query.message.reply_text(
                    "❌ У вас нет доступа для создания ключа.\n\n"
                    "Вы можете:\n"
                    "• 💳 Купить доступ через меню \"💳 Оплатить VPN\"\n"
                    "• 🔓 Запросить активацию у администратора",
                    reply_markup=reply_keyboard
                )
                return

            # Генерируем имя ключа с информацией о пользователе
            # Формат: имя_телефон_дата_ID
            user_name = (db_user.first_name or db_user.username or f"user{db_user.telegram_id}").replace(" ", "_").replace("-", "_")[:15]
            phone_part = db_user.phone_number.replace("+", "plus").replace("-", "")[:10] if db_user.phone_number else "nophone"
            date_part = datetime.now().strftime("%Y%m%d_%H%M")
            
            # Ограничиваем длину имени (WireGuard может иметь ограничения)
            key_name = f"{user_name}_{phone_part}_{date_part}_{db_user.telegram_id}"
            # Ограничиваем максимальную длину (например, 60 символов, но оставляем место для префикса)
            if len(key_name) > 60:
                # Обрезаем имя пользователя если нужно
                max_user_len = 60 - len(f"_{phone_part}_{date_part}_{db_user.telegram_id}")
                user_name = user_name[:max_user_len] if max_user_len > 0 else "user"
                key_name = f"{user_name}_{phone_part}_{date_part}_{db_user.telegram_id}"
            
            logger.info(f"Generated key name: {key_name} for user {db_user.telegram_id}")

            # Показываем сообщение о создании
            msg = await query.message.reply_text("⏳ Создание VPN ключа...")

            if not hasattr(vpn_manager, "create_vpn_key_async"):
                logger.error("VPNManager missing create_vpn_key_async method on server")
                reply_keyboard = self._get_reply_keyboard()
                await msg.edit_text(
                    "❌ Сервер еще не обновлен до последней версии.\n"
                    "Попросите администратора перезапустить сервисы после деплоя."
                )
                await query.message.reply_text(
                    "Откройте меню через кнопку ниже и попробуйте позже.",
                    reply_markup=reply_keyboard
                )
                return

            # Создаем ключ (асинхронно, чтобы не блокировать event loop)
            try:
                vpn_data = await vpn_manager.create_vpn_key_async(db_user.id, key_name)
            except Exception as e:
                logger.error(f"Error in create_vpn_key: {e}", exc_info=True)
                error_msg = str(e)
                
                # Формируем понятное сообщение об ошибке
                if "SSH" in error_msg or "подключение" in error_msg.lower():
                    user_error_msg = (
                        "❌ Ошибка при генерации ключа.\n\n"
                        "Не удалось подключиться к серверу.\n"
                        "Проверьте SSH подключение и настройки."
                    )
                elif "публичный ключ" in error_msg.lower():
                    user_error_msg = (
                        "❌ Ошибка при генерации ключа.\n\n"
                        "Не удалось получить публичный ключ сервера.\n"
                        "Проверьте, что Docker контейнер работает."
                    )
                elif "IP" in error_msg or "адрес" in error_msg.lower():
                    user_error_msg = (
                        "❌ Ошибка при генерации ключа.\n\n"
                        "Нет доступных IP адресов в сети.\n"
                        "Обратитесь к администратору."
                    )
                else:
                    user_error_msg = (
                        "❌ Ошибка при генерации ключа.\n\n"
                        "Проверьте подключение к серверу и настройки VPN.\n"
                        "Детали ошибки записаны в лог."
                    )
                
                reply_keyboard = self._get_reply_keyboard()
                await msg.edit_text(user_error_msg, reply_markup=reply_keyboard)
                return

            if not vpn_data:
                error_msg = (
                    "❌ Ошибка при генерации ключа.\n\n"
                    "Проверьте подключение к серверу и настройки VPN."
                )
                reply_keyboard = self._get_reply_keyboard()
                await msg.edit_text(error_msg, reply_markup=reply_keyboard)
                return

            # Сохраняем в БД с правильной привязкой к платежу
            vpn_key = VPNKey(
                user_id=db_user.id,
                key_name=key_name,
                config_file_path=str(vpn_data['config_path']),
                qr_code_path=str(vpn_data['qr_path']) if vpn_data['qr_path'] else None,
                protocol='amneziawg',
                client_ip=vpn_data['client_ip'],
                public_key=vpn_data['public_key'],
                private_key=vpn_data['private_key'],  # В продакшене лучше зашифровать
                is_active=True,
                created_by_bot=True,  # Ключ создан через бота
                access_type='paid' if is_paid_user else 'free',  # Тип доступа
                payment_id=payment_with_codes.id if payment_with_codes else None,  # Привязка к платежу для платных
                purchase_date=payment_with_codes.paid_at if payment_with_codes else datetime.now(),
                subscription_period_days=payment_with_codes.subscription_period_days if payment_with_codes else None,
                expires_at=payment_with_codes.expires_at if payment_with_codes else None,
                is_test=False
            )
            db.add(vpn_key)
            db.commit()

            # Отправляем файлы пользователю
            reply_keyboard = self._get_reply_keyboard()
            await msg.edit_text("✅ VPN ключ успешно создан!")

            # Отправляем конфигурационный файл
            with open(vpn_data['config_path'], 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=f"{key_name}.conf",
                    caption=f"🔐 Ваш VPN ключ: {key_name}",
                    reply_markup=reply_keyboard
                )

            # Отправляем QR-код, если есть
            if vpn_data['qr_path'] and Path(vpn_data['qr_path']).exists():
                with open(vpn_data['qr_path'], 'rb') as f:
                    await query.message.reply_photo(
                        photo=f,
                        caption="📱 Отсканируйте QR-код для быстрой настройки",
                        reply_markup=reply_keyboard
                    )

            # Читаем содержимое конфигурации для отправки текстом
            with open(vpn_data['config_path'], 'r', encoding='utf-8') as f:
                config_text = f.read()
            
            # Инструкции
            instructions = (
                "📖 Инструкция по использованию:\n\n"
                "1. Скачайте приложение Amnezia VPN\n"
                "2. Откройте приложение и нажмите \"Импорт\"\n"
                "3. Выберите файл конфигурации (.conf) или отсканируйте QR-код\n"
                "4. Или скопируйте текст конфигурации ниже\n"
                "5. Подключитесь к VPN"
            )
            await query.message.reply_text(instructions, reply_markup=reply_keyboard)
            
            # Отправляем текст конфигурации
            config_message = (
                "📋 Текст конфигурации (для копирования):\n\n"
                "```\n"
                f"{config_text}\n"
                "```"
            )
            await query.message.reply_text(config_message, parse_mode='Markdown', reply_markup=reply_keyboard)

        except Exception as e:
            logger.error(f"Error creating key: {e}")
            reply_keyboard = self._get_reply_keyboard()
            await query.message.reply_text("❌ Произошла ошибка при создании ключа.", reply_markup=reply_keyboard)
        finally:
            db.close()

    async def _handle_my_keys(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Показ списка ключей пользователя"""
        query = update.callback_query

        db = get_db_session()
        try:
            keys = db.query(VPNKey).filter(
                VPNKey.user_id == db_user.id,
                VPNKey.is_active == True
            ).order_by(VPNKey.created_at.desc()).all()

            active_keys_count = len(keys)
            max_keys = db_user.max_keys

            if not keys:
                text = f"📋 У вас пока нет VPN ключей.\n\nВы можете создать до {max_keys} ключей."
                keyboard = [
                    [InlineKeyboardButton("🔐 Создать ключ", callback_data="create_key")],
                    [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)
                return

            text = f"📋 Ваши VPN ключи ({active_keys_count}/{max_keys}):\n\n"

            keyboard = []
            for key in keys:
                created_date = key.created_at.strftime("%d.%m.%Y %H:%M")
                last_used = f"\nИспользован: {key.last_used.strftime('%d.%m.%Y %H:%M')}" if key.last_used else ""

                text += (
                    f"🔑 {key.key_name}\n"
                    f"Протокол: {key.protocol}\n"
                    f"Создан: {created_date}{last_used}\n\n"
                )

                # Сокращаем имя ключа для кнопки (максимум 25 символов)
                key_display_name = key.key_name
                if len(key_display_name) > 25:
                    # Берем последние 25 символов с ...
                    key_display_name = "..." + key_display_name[-22:]
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"🗑 Удалить {key_display_name}",
                        callback_data=f"delete_key:{key.id}"
                    )
                ])

            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error showing keys: {e}")
            reply_keyboard = self._get_reply_keyboard()
            await query.message.reply_text("❌ Произошла ошибка при загрузке ключей.", reply_markup=reply_keyboard)
        finally:
            db.close()

    async def _handle_delete_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  db_user: User, key_id: int):
        """Удаление VPN ключа"""
        query = update.callback_query

        if not key_id:
            await query.answer("❌ Не указан ID ключа.", show_alert=True)
            return

        db = get_db_session()
        try:
            key = db.query(VPNKey).filter(
                VPNKey.id == key_id,
                VPNKey.user_id == db_user.id
            ).first()

            if not key:
                await query.answer("❌ Ключ не найден.", show_alert=True)
                return

            # Показываем подтверждение удаления
            await query.answer("⏳ Удаление ключа...")

            # Удаляем с сервера (асинхронно)
            try:
                if key.public_key:
                    await vpn_manager.delete_vpn_key_async(key.public_key, key.key_name)
                else:
                    logger.warning(f"Key {key.key_name} has no public_key, skipping server deletion")
            except Exception as e:
                logger.error(f"Error deleting key from server: {e}")

            # Удаляем из БД
            key_name = key.key_name
            db.delete(key)
            db.commit()

            await query.answer(f"✅ Ключ {key_name} успешно удален.", show_alert=True)

            # Показываем обновленный список ключей
            await self._handle_my_keys(update, context, db_user)

        except Exception as e:
            logger.error(f"Error deleting key: {e}", exc_info=True)
            reply_keyboard = self._get_reply_keyboard()
            await query.message.reply_text("❌ Произошла ошибка при удалении ключа.", reply_markup=reply_keyboard)
            await query.answer("❌ Произошла ошибка при удалении ключа.", show_alert=True)
        finally:
            db.close()

    async def _handle_admin_web_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Генерация токена и открытие веб-панели"""
        query = update.callback_query
        await query.answer()
        
        try:
            # Генерируем токен через FastAPI backend
            web_admin_url = WEB_SERVER_URL.replace(":8888", ":8889")  # FastAPI на порту 8889
            token_request = {
                "telegram_id": db_user.telegram_id
            }
            
            try:
                # Генерируем токен через FastAPI backend (с retry)
                response = await self._make_http_request_with_retry(
                    'POST',
                    f"{web_admin_url}/api/auth/token",
                    json=token_request,
                    timeout=15
                )
                
                if response.status_code == 200:
                    result = response.json()
                    token = result.get('token')
                    expires_at = result.get('expires_at')
                    
                    # Формируем ссылку на веб-панель
                    web_panel_url = f"{web_admin_url}/?token={token}"
                    
                    text = (
                        f"🌐 Веб-панель администрирования\n\n"
                        f"Токен действителен до: {expires_at}\n"
                        f"(24 часа)\n\n"
                        f"Нажмите на кнопку ниже, чтобы открыть веб-панель:"
                    )
                    
                    keyboard = [
                        [InlineKeyboardButton("🌐 Открыть веб-панель", url=web_panel_url)],
                        [InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)
                else:
                    logger.error(f"Failed to generate web panel token: {response.status_code}, {response.text}")
                    await query.message.reply_text(
                        "❌ Ошибка при создании токена для веб-панели. Попробуйте позже."
                    )
            except requests.exceptions.RequestException as e:
                logger.error(f"Error connecting to web admin API: {e}")
                await query.message.reply_text(
                    "❌ Сервис веб-панели временно недоступен. Попробуйте позже."
                )
        
        except Exception as e:
            logger.error(f"Error generating web panel token: {e}", exc_info=True)
            await query.message.reply_text("❌ Произошла ошибка.")

    async def _handle_admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Главное меню админ-панели"""
        query = update.callback_query

        db = get_db_session()
        try:
            total_users = db.query(User).count()
            active_users = db.query(User).filter(User.is_active == True).count()
            total_keys = db.query(VPNKey).filter(VPNKey.is_active == True).count()

            text = (
                f"⚙️ Админ-панель\n\n"
                f"📊 Статистика:\n"
                f"• Всего пользователей: {total_users}\n"
                f"• Активных пользователей: {active_users}\n"
                f"• Всего ключей: {total_keys}"
            )

            keyboard = [
                [InlineKeyboardButton("🌐 Веб-панель", callback_data="admin_web_panel")],
                [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
                [InlineKeyboardButton("🔑 Все ключи", callback_data="admin_all_keys")],
                [InlineKeyboardButton("⚙️ Настройки приложения", callback_data="admin_settings")],
                [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
                [InlineKeyboardButton("🔄 Синхронизировать ключи", callback_data="admin_sync_keys")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in admin panel: {e}", exc_info=True)
            await query.message.reply_text("❌ Произошла ошибка.")
        finally:
            db.close()

    async def _handle_admin_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User, page: int = 0):
        """Управление пользователями (список с пагинацией)"""
        query = update.callback_query
        users_per_page = 10

        db = get_db_session()
        try:
            # Фильтруем удаленных пользователей
            all_users = db.query(User).filter(User.is_deleted == False).order_by(User.created_at.desc()).all()
            total_users = len(all_users)
            total_pages = (total_users + users_per_page - 1) // users_per_page if total_users > 0 else 1
            page = max(0, min(page, total_pages - 1))

            start_idx = page * users_per_page
            end_idx = start_idx + users_per_page
            page_users = all_users[start_idx:end_idx]

            # Упрощенное текстовое сообщение - только информация о странице
            text = f"👥 Пользователи (Страница {page + 1}/{total_pages})"

            keyboard = []
            for user in page_users:
                # Считаем количество ключей пользователя
                keys_count = db.query(VPNKey).filter(
                    VPNKey.user_id == user.id,
                    VPNKey.is_active == True
                ).count()

                status = "✅" if user.is_active else "❌"
                admin_icon = "👑" if user.is_admin else ""
                display_name = self._get_user_display_name_with_username(user)

                # Форматируем имя для кнопки с информацией о ключах
                # Включаем статус и иконку админа в кнопку
                button_text = self._format_user_button_name(
                    f"{status} {admin_icon} {display_name}".strip(),
                    keys_count,
                    user.max_keys
                )
                
                keyboard.append([
                    InlineKeyboardButton(
                        button_text,
                        callback_data=f"admin_user_detail:{user.id}"
                    )
                ])

            # Кнопки навигации
            nav_buttons = []
            if total_pages > 1:
                if page > 0:
                    nav_buttons.append(InlineKeyboardButton("◀️ Пред.", callback_data=f"admin_user_page:{page - 1}"))
                if page < total_pages - 1:
                    nav_buttons.append(InlineKeyboardButton("След. ▶️", callback_data=f"admin_user_page:{page + 1}"))

            if nav_buttons:
                keyboard.append(nav_buttons)

            keyboard.append([InlineKeyboardButton("➕ Добавить пользователя", callback_data="admin_add_user")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in admin users: {e}", exc_info=True)
            await query.message.reply_text("❌ Произошла ошибка.")
        finally:
            db.close()

    async def _handle_admin_user_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User, user_id: int):
        """Детали пользователя"""
        query = update.callback_query

        db = get_db_session()
        try:
            target_user = db.query(User).filter(User.id == user_id).first()
            if not target_user:
                await query.answer("❌ Пользователь не найден.", show_alert=True)
                return

            # Получаем список ключей пользователя
            user_keys = db.query(VPNKey).filter(
                VPNKey.user_id == target_user.id,
                VPNKey.is_active == True
            ).order_by(VPNKey.created_at.desc()).all()

            keys_count = len(user_keys)
            status = "✅ Активен" if target_user.is_active else "❌ Неактивен"
            admin_status = "✅ Да" if target_user.is_admin else "❌ Нет"

            display_name = self._get_user_display_name_with_username(target_user)
            text = (
                f"👤 Детали пользователя\n\n"
                f"Имя: {display_name}\n"
                f"Полное имя: {target_user.first_name or 'Не указано'} {target_user.last_name or ''}\n"
                f"Telegram ID: {target_user.telegram_id}\n"
                f"Телефон: {target_user.phone_number or 'не указан'}\n"
                f"Статус: {status}\n"
                f"Администратор: {admin_status}\n"
                f"Ключей: {keys_count}/{target_user.max_keys}\n"
                f"Создан: {target_user.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )

            if user_keys:
                text += "🔑 Ключи:\n"
                for key in user_keys[:10]:  # Показываем максимум 10 ключей
                    text += f"• {key.key_name}\n"
                if len(user_keys) > 10:
                    text += f"... и еще {len(user_keys) - 10} ключей\n"
            else:
                text += "🔑 Ключи: нет\n"

            keyboard = [
                [
                    InlineKeyboardButton("➕ +1", callback_data=f"admin_set_limit:{target_user.id}:{target_user.max_keys + 1}"),
                    InlineKeyboardButton("➖ -1", callback_data=f"admin_set_limit:{target_user.id}:{max(1, target_user.max_keys - 1)}")
                ],
                [
                    InlineKeyboardButton("1", callback_data=f"admin_set_limit:{target_user.id}:1"),
                    InlineKeyboardButton("3", callback_data=f"admin_set_limit:{target_user.id}:3"),
                    InlineKeyboardButton("5", callback_data=f"admin_set_limit:{target_user.id}:5"),
                    InlineKeyboardButton("10", callback_data=f"admin_set_limit:{target_user.id}:10"),
                    InlineKeyboardButton("20", callback_data=f"admin_set_limit:{target_user.id}:20"),
                    InlineKeyboardButton("50", callback_data=f"admin_set_limit:{target_user.id}:50")
                ],
                [InlineKeyboardButton("🗑 Удалить пользователя", callback_data=f"admin_delete_user:{target_user.id}")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_users")]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in admin user detail: {e}", exc_info=True)
            await query.message.reply_text("❌ Произошла ошибка.")
        finally:
            db.close()

    async def _handle_admin_set_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User, user_id: int, limit: int):
        """Изменение лимита ключей пользователя"""
        query = update.callback_query

        db = get_db_session()
        try:
            target_user = db.query(User).filter(User.id == user_id).first()
            if not target_user:
                await query.answer("❌ Пользователь не найден.", show_alert=True)
                return

            limit = max(1, limit)  # Минимум 1
            target_user.max_keys = limit
            db.commit()

            await query.answer(f"✅ Лимит ключей установлен: {limit}", show_alert=True)
            # Обновляем экран деталей пользователя
            await self._handle_admin_user_detail(update, context, db_user, user_id)

        except Exception as e:
            logger.error(f"Error setting limit: {e}", exc_info=True)
            await query.answer("❌ Произошла ошибка.", show_alert=True)
        finally:
            db.close()

    async def _handle_admin_delete_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User, user_id: int):
        """Удаление пользователя"""
        query = update.callback_query

        if user_id == db_user.id:
            await query.answer("❌ Нельзя удалить самого себя.", show_alert=True)
            return

        db = get_db_session()
        try:
            target_user = db.query(User).filter(User.id == user_id).first()
            if not target_user:
                await query.answer("❌ Пользователь не найден.", show_alert=True)
                return

            # Удаляем все ключи пользователя
            user_keys = db.query(VPNKey).filter(VPNKey.user_id == user_id).all()
            # Удаляем ключи с сервера асинхронно
            delete_tasks = []
            for key in user_keys:
                if key.public_key:
                    delete_tasks.append(vpn_manager.delete_vpn_key_async(key.public_key, key.key_name))
            
            # Выполняем все удаления параллельно
            if delete_tasks:
                results = await asyncio.gather(*delete_tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Error deleting key from server: {result}")

            # Удаляем пользователя (каскадное удаление ключей)
            db.delete(target_user)
            db.commit()

            await query.answer(f"✅ Пользователь {target_user.first_name or 'удален'} удален", show_alert=True)
            # Возвращаемся к списку пользователей
            await self._handle_admin_users(update, context, db_user, page=0)

        except Exception as e:
            logger.error(f"Error deleting user: {e}", exc_info=True)
            await query.answer("❌ Произошла ошибка при удалении.", show_alert=True)
        finally:
            db.close()

    async def _handle_admin_add_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Добавление пользователя"""
        query = update.callback_query

        text = (
            "➕ Добавить пользователя\n\n"
            "Отправьте:\n"
            "• Номер телефона (+79001234567)\n"
            "• Или Telegram ID (123456789)\n\n"
            "Пример: +79001234567 или 123456789"
        )

        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_users")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)
        # Сохраняем состояние ожидания ввода пользователя
        context.user_data['admin_adding_user'] = True
        logger.info(f"Set admin_adding_user flag to True for user {db_user.telegram_id}")
        logger.info(f"context.user_data after setting: {list(context.user_data.keys())}")

    async def _handle_admin_all_keys(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User, page: int = 0):
        """Все ключи (всех пользователей) с пагинацией"""
        query = update.callback_query
        keys_per_page = 8

        db = get_db_session()
        try:
            keys_query = db.query(VPNKey).filter(VPNKey.is_active == True).order_by(VPNKey.created_at.desc())
            total_keys = keys_query.count()
            total_pages = max(1, (total_keys + keys_per_page - 1) // keys_per_page)
            page = max(0, min(page, total_pages - 1))
            context.user_data['admin_keys_page'] = page

            page_keys = keys_query.offset(page * keys_per_page).limit(keys_per_page).all()

            text = (
                "🔑 Все активные ключи\n"
                f"Страница {page + 1}/{total_pages}\n"
                f"Всего ключей: {total_keys}\n\n"
                "Нажмите на кнопку, чтобы удалить ключ."
            )

            if not page_keys:
                text += "\n\nНа этой странице пока ничего нет."

            keyboard = []
            for key in page_keys:
                owner = self._get_user_display_name_with_username(key.user)
                button_label = f"🗑 {key.key_name[:18]} • {owner[:20]}"
                keyboard.append([
                    InlineKeyboardButton(
                        button_label,
                        callback_data=f"admin_delete_key:{key.id}"
                    )
                ])

            if total_pages > 1:
                nav_buttons = []
                if page > 0:
                    nav_buttons.append(InlineKeyboardButton("◀️ Пред.", callback_data=f"admin_all_keys_page:{page - 1}"))
                if page < total_pages - 1:
                    nav_buttons.append(InlineKeyboardButton("След. ▶️", callback_data=f"admin_all_keys_page:{page + 1}"))
                if nav_buttons:
                    keyboard.append(nav_buttons)

            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in admin all keys: {e}", exc_info=True)
            await query.message.reply_text("❌ Произошла ошибка.")
        finally:
            db.close()

    async def _handle_admin_delete_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User, key_id: int):
        """Удаление ключа администратором"""
        query = update.callback_query

        db = get_db_session()
        try:
            key = db.query(VPNKey).filter(VPNKey.id == key_id).first()
            if not key:
                await query.answer("❌ Ключ не найден.", show_alert=True)
                return

            key_name = key.key_name
            user_name = key.user.first_name or "Пользователь"

            # Удаляем с сервера (асинхронно)
            if key.public_key:
                try:
                    await vpn_manager.delete_vpn_key_async(key.public_key, key.key_name)
                except Exception as e:
                    logger.error(f"Error deleting key from server: {e}")

            # Удаляем из БД
            db.delete(key)
            db.commit()

            await query.answer(f"✅ Ключ {key_name} удален", show_alert=True)
            # Обновляем список ключей, сохраняя текущую страницу
            current_page = context.user_data.get('admin_keys_page', 0)
            await self._handle_admin_all_keys(update, context, db_user, page=current_page)

        except Exception as e:
            logger.error(f"Error deleting key: {e}", exc_info=True)
            await query.answer("❌ Произошла ошибка при удалении.", show_alert=True)
        finally:
            db.close()

    async def _handle_admin_sync_keys(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Синхронизация ключей с сервером"""
        query = update.callback_query

        db = get_db_session()
        try:
            await query.answer("⏳ Синхронизация ключей...")
            
            # Выполняем синхронизацию
            stats = vpn_manager.sync_keys_with_server(db)
            
            # Формируем сообщение
            text = "🔄 Синхронизация ключей завершена\n\n"
            
            if stats['added_from_server'] > 0:
                text += f"✅ Добавлено с сервера: {stats['added_from_server']}\n"
            
            if stats['removed_from_server'] > 0:
                text += f"⚠️ Помечено как неактивные: {stats['removed_from_server']}\n"
            
            if stats['added_from_server'] == 0 and stats['removed_from_server'] == 0:
                text += "✅ Ключи синхронизированы. Изменений нет.\n"
            
            if stats['errors']:
                text += f"\n❌ Ошибок: {len(stats['errors'])}\n"
                for error in stats['errors'][:3]:  # Показываем первые 3 ошибки
                    text += f"• {error[:50]}...\n"
            
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(text=text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error syncing keys: {e}", exc_info=True)
            await query.answer("❌ Произошла ошибка при синхронизации.", show_alert=True)
        finally:
            db.close()

    async def _handle_admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Расширенная статистика"""
        query = update.callback_query

        db = get_db_session()
        try:
            # Статистика по пользователям
            total_users = db.query(User).count()
            active_users = db.query(User).filter(User.is_active == True).count()
            admin_users = db.query(User).filter(User.is_admin == True).count()

            # Статистика по ключам
            total_keys = db.query(VPNKey).filter(VPNKey.is_active == True).count()
            from sqlalchemy import func as sql_func
            keys_by_protocol = db.query(VPNKey.protocol, sql_func.count(VPNKey.id)).filter(
                VPNKey.is_active == True
            ).group_by(VPNKey.protocol).all()

            # Статистика использования
            # Среднее количество ключей на пользователя
            from sqlalchemy import func as sql_func
            user_keys_counts_query = db.query(
                VPNKey.user_id, sql_func.count(VPNKey.id).label('keys_count')
            ).filter(
                VPNKey.is_active == True
            ).group_by(VPNKey.user_id).all()
            
            avg_keys = 0
            max_keys_result = 0
            if user_keys_counts_query:
                counts = [row.keys_count for row in user_keys_counts_query]
                avg_keys = sum(counts) / len(counts) if counts else 0
                max_keys_result = max(counts) if counts else 0

            text = "📊 Статистика\n\n"

            text += "👥 Пользователи:\n"
            text += f"• Всего: {total_users}\n"
            text += f"• Активных: {active_users}\n"
            text += f"• Администраторов: {admin_users}\n\n"

            text += "🔑 Ключи:\n"
            text += f"• Всего активных: {total_keys}\n"
            if keys_by_protocol:
                text += "• По протоколам:\n"
                for protocol, count in keys_by_protocol:
                    text += f"  • {protocol}: {count}\n"
            text += "\n"

            text += "📈 Использование:\n"
            text += f"• Среднее ключей на пользователя: {avg_keys:.1f}\n"
            text += f"• Максимум ключей у пользователя: {max_keys_result}\n"

            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in admin stats: {e}", exc_info=True)
            await query.message.reply_text("❌ Произошла ошибка.")
        finally:
            db.close()

    async def _handle_admin_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Главное меню настроек приложения"""
        query = update.callback_query

        text = "⚙️ Настройки приложения\n\nВыберите категорию настроек:"

        keyboard = [
            [InlineKeyboardButton("📱 Telegram", callback_data="admin_settings_category:telegram")],
            [InlineKeyboardButton("💳 YooMoney", callback_data="admin_settings_category:yoomoney")],
            [InlineKeyboardButton("🔐 VPN", callback_data="admin_settings_category:vpn")],
            [InlineKeyboardButton("🌐 Общие", callback_data="admin_settings_category:general")],
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)

    async def _handle_admin_settings_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                              db_user: User, category: str):
        """Список настроек по категории"""
        query = update.callback_query

        settings = config_manager.get_all(category=category)
        
        category_names = {
            'telegram': '📱 Telegram',
            'yoomoney': '💳 YooMoney',
            'vpn': '🔐 VPN',
            'general': '🌐 Общие'
        }
        
        text = f"{category_names.get(category, category)} - Настройки\n\n"
        
        keyboard = []
        if settings:
            for setting in settings:
                value_display = setting['value'] if setting['value'] else "(не задано)"
                if len(value_display) > 40:
                    value_display = value_display[:37] + "..."
                
                text += f"🔧 {setting['key']}\n"
                text += f"   Значение: {value_display}\n"
                if setting['description']:
                    text += f"   Описание: {setting['description']}\n"
                text += "\n"
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"✏️ {setting['key']}",
                        callback_data=f"admin_setting_edit:{setting['key']}"
                    )
                ])
        else:
            text += "Настроек в этой категории пока нет.\n\n"
        
        # Добавляем кнопку для добавления настройки (только если это не yoomoney, там только CLIENT_ID)
        if category != 'yoomoney':
            keyboard.append([InlineKeyboardButton("➕ Добавить настройку", callback_data=f"admin_setting_add:{category}")])
        
        # Шаблоны для популярных настроек (показываем только если настройка еще не добавлена)
        if category == 'yoomoney':
            existing_keys = [s['key'] for s in settings] if settings else []
            
            # Шаблоны доступных настроек
            templates = [
                ('YMONEY_CLIENT_ID', 'ID приложения YooMoney', '⚠️ Обязательная настройка'),
                ('YMONEY_WALLET', 'Номер кошелька YooMoney', '💡 Опционально (для QuickPay)'),
            ]
            
            # Показываем только те шаблоны, которых еще нет
            new_templates = [t for t in templates if t[0] not in existing_keys]
            
            if new_templates:
                text += "\n📋 Доступные настройки:\n\n"
                for key, desc, note in new_templates:
                    text += f"{note}\n"
                    keyboard.append([
                        InlineKeyboardButton(
                            f"➕ {desc}",
                            callback_data=f"admin_setting_add_template:{category}:{key}"
                        )
                    ])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_settings")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)

    async def _handle_admin_setting_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                         db_user: User, setting_key: str):
        """Редактирование настройки"""
        query = update.callback_query
        
        current_value = config_manager.get(setting_key, "")
        
        text = (
            f"✏️ Редактирование настройки\n\n"
            f"Ключ: `{setting_key}`\n"
            f"Текущее значение: `{current_value}`\n\n"
            f"Отправьте новое значение текстом или нажмите кнопку для отмены."
        )
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="admin_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup, parse_mode='Markdown')
        context.user_data['admin_editing_setting'] = setting_key

    async def _handle_admin_setting_edit_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                               db_user: User, setting_key: str, new_value: str):
        """Обработка нового значения настройки"""
        categories = {
            'BOT_TOKEN': ('telegram', 'Токен Telegram бота'),
            'YMONEY_CLIENT_ID': ('yoomoney', 'YooMoney Client ID'),
            'WEB_SERVER_DOMAIN': ('general', 'Домен веб-сервера'),
        }
        
        category, description = categories.get(setting_key, ('general', 'Настройка приложения'))
        is_secret = setting_key == 'BOT_TOKEN'
        
        if config_manager.set(setting_key, new_value, description=description, 
                              is_secret=is_secret, category=category):
            config_manager.clear_cache()
            await update.message.reply_text(
                f"✅ Настройка `{setting_key}` успешно обновлена!",
                parse_mode='Markdown'
            )
            context.user_data.pop('admin_editing_setting', None)
            keyboard = [[InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
                       [InlineKeyboardButton("◀️ Админ-панель", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
        else:
            await update.message.reply_text(f"❌ Ошибка при сохранении настройки", parse_mode='Markdown')

    async def _handle_admin_setting_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                           db_user: User, setting_key: str):
        """Удаление настройки"""
        query = update.callback_query
        
        if config_manager.delete(setting_key):
            config_manager.clear_cache()
            await query.answer(f"✅ Настройка {setting_key} удалена", show_alert=True)
            await self._handle_admin_settings(update, context, db_user)
        else:
            await query.answer("❌ Ошибка при удалении настройки", show_alert=True)

    async def _handle_admin_setting_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                        db_user: User, category: str):
        """Добавление новой настройки"""
        query = update.callback_query
        
        text = (
            f"➕ Добавление новой настройки\n\n"
            f"Категория: {category}\n\n"
            f"Отправьте в формате:\n"
            f"`ключ=значение`\n\n"
            f"Пример:\n"
            f"`YMONEY_CLIENT_ID=ED3F92226A61D36D60400C8DF4E3E89064A597DA345FE9E286741685E5154B2E`\n\n"
            f"Или отправьте просто ключ, затем бот попросит ввести значение."
        )
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data=f"admin_settings_category:{category}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup, parse_mode='Markdown')
        
        # Сохраняем состояние добавления настройки
        context.user_data['admin_adding_setting'] = category

    async def _handle_admin_setting_add_template(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                                  db_user: User, category: str, template_key: str):
        """Добавление настройки из шаблона"""
        query = update.callback_query
        
        templates = {
            'YMONEY_CLIENT_ID': ('yoomoney', 'ID приложения YooMoney', False),
            'YMONEY_WALLET': ('yoomoney', 'Номер кошелька YooMoney', False),
            'BOT_TOKEN': ('telegram', 'Токен Telegram бота', True),
            'WEB_SERVER_DOMAIN': ('general', 'Домен веб-сервера', False),
        }
        
        if template_key in templates:
            cat, desc, is_secret = templates[template_key]
            text = (
                f"➕ Добавление настройки\n\n"
                f"Ключ: `{template_key}`\n"
                f"Описание: {desc}\n"
                f"Категория: {cat}\n\n"
                f"Отправьте значение для этой настройки:"
            )
            
            keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data=f"admin_settings_category:{category}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup, parse_mode='Markdown')
            
            # Сохраняем информацию о добавляемой настройке
            context.user_data['admin_adding_setting'] = category
            context.user_data['admin_adding_setting_key'] = template_key
            context.user_data['admin_adding_setting_desc'] = desc
            context.user_data['admin_adding_setting_secret'] = is_secret
        else:
            await query.answer("❌ Неизвестный шаблон настройки", show_alert=True)

    async def _handle_admin_setting_add_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                              db_user: User, category: str, setting_key: str, 
                                              new_value: str, description: str = None, is_secret: bool = False):
        """Обработка добавления новой настройки"""
        if config_manager.set(setting_key, new_value, description=description or f'Настройка {setting_key}',
                              is_secret=is_secret, category=category):
            config_manager.clear_cache()
            await update.message.reply_text(
                f"✅ Настройка `{setting_key}` успешно добавлена!\n\n"
                f"Категория: {category}\n"
                f"Значение: `{new_value if not is_secret else '***'}`",
                parse_mode='Markdown'
            )
            # Очищаем флаги
            context.user_data.pop('admin_adding_setting', None)
            context.user_data.pop('admin_adding_setting_key', None)
            context.user_data.pop('admin_adding_setting_desc', None)
            context.user_data.pop('admin_adding_setting_secret', None)
            
            # Возвращаемся к настройкам категории
            keyboard = [[InlineKeyboardButton("⚙️ Настройки категории", callback_data=f"admin_settings_category:{category}")],
                       [InlineKeyboardButton("◀️ Админ-панель", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
        else:
            await update.message.reply_text(f"❌ Ошибка при добавлении настройки `{setting_key}`", parse_mode='Markdown')

    async def _show_donation_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Показ меню выбора суммы доната"""
        query = update.callback_query
        await query.answer()
        
        text = (
            "💚 Поддержать проект\n\n"
            "Ваша поддержка помогает поддерживать работу VPN сервера для друзей администратора.\n\n"
            "⚠️ Минимальная сумма: 250 ₽\n"
            "➕ Комиссия: 2%\n\n"
            "Выберите сумму пожертвования:"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("250 ₽", callback_data="donation_amount:250"),
            ],
            [
                InlineKeyboardButton("500 ₽", callback_data="donation_amount:500"),
            ],
            [
                InlineKeyboardButton("1000 ₽", callback_data="donation_amount:1000"),
            ],
            [
                InlineKeyboardButton("💵 Другая сумма", callback_data="donation_custom"),
            ],
            [
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)
    
    async def _handle_donation_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User, amount: int):
        """Обработка оплаты доната с выбранной суммой"""
        query = update.callback_query
        await query.answer()
        
        db = get_db_session()
        try:
            # Генерируем платежную ссылку через Flask сервер
            payment_data = {
                'user_id': db_user.id,
                'amount': amount,
                'description': f'Пожертвование на поддержку VPN сервера от {db_user.nickname or db_user.first_name or db_user.username or f"user_{db_user.telegram_id}"}',
                'payment_type': 'donation'
            }
            
            try:
                # Вызываем Flask сервер для генерации платежной ссылки (с retry)
                response = await self._make_http_request_with_retry(
                    'POST',
                    f"{WEB_SERVER_URL}/generate_payment_uri",
                    json=payment_data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    payment_url = result.get('payment_url')
                    payment_label = result.get('payment_label')
                    
                    # Сохраняем payment_id для проверки баланса
                    context.user_data['payment_id'] = result.get('payment_id')
                    context.user_data['payment_label'] = payment_label
                    context.user_data['payment_amount'] = amount
                    
                    text = (
                        f"💚 Пожертвование на поддержку проекта\n\n"
                        f"Сумма: {amount} ₽\n"
                        f"➕ Комиссия (2%): {result.get('commission', 0):.2f} ₽\n"
                        f"💰 Итого к оплате: {result.get('amount_with_commission', amount):.2f} ₽\n\n"
                        f"Спасибо за вашу поддержку! 🙏\n\n"
                        f"Нажмите на кнопку ниже, чтобы перейти к оплате:"
                    )
                    
                    keyboard = [
                        [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
                        [InlineKeyboardButton("✅ Проверить баланс", callback_data="check_payment_balance")],
                        [InlineKeyboardButton("◀️ Назад к выбору суммы", callback_data="pay_vpn")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)
                else:
                    logger.error(f"Failed to generate payment URL: {response.status_code}, {response.text}")
                    reply_keyboard = self._get_reply_keyboard()
                    await query.message.reply_text(
                        "❌ Ошибка при создании платежной ссылки. Попробуйте позже или обратитесь к администратору.",
                        reply_markup=reply_keyboard
                    )
            except requests.exceptions.RequestException as e:
                logger.error(f"Error connecting to payment server: {e}")
                reply_keyboard = self._get_reply_keyboard()
                await query.message.reply_text(
                    "❌ Сервис оплаты временно недоступен. Попробуйте позже или обратитесь к администратору.",
                    reply_markup=reply_keyboard
                )
        finally:
            db.close()
    
    async def _handle_custom_donation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Обработка запроса на ввод произвольной суммы доната"""
        query = update.callback_query
        await query.answer()
        
        text = (
            "💵 Введите сумму пожертвования\n\n"
            "Отправьте сумму в рублях (например: 150 или 2500)\n"
            "Минимальная сумма: 10 ₽\n"
            "Максимальная сумма: 100000 ₽\n\n"
            "Или нажмите кнопку ниже, чтобы вернуться к выбору суммы:"
        )
        
        keyboard = [
            [InlineKeyboardButton("◀️ Назад к выбору суммы", callback_data="pay_vpn")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)
        
        # Устанавливаем состояние ожидания ввода суммы
        context.user_data['waiting_for_donation_amount'] = True
    
    async def _handle_donation_amount_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User, text: str):
        """Обработка ввода произвольной суммы доната"""
        try:
            # Парсим сумму
            amount = int(text.strip())
            
            # Проверяем диапазон
            reply_keyboard = self._get_reply_keyboard()
            if amount < 10:
                await update.message.reply_text(
                    "❌ Минимальная сумма пожертвования: 10 ₽\n\n"
                    "Пожалуйста, введите сумму от 10 до 100000 ₽:",
                    reply_markup=reply_keyboard
                )
                return
            
            if amount > 100000:
                await update.message.reply_text(
                    "❌ Максимальная сумма пожертвования: 100000 ₽\n\n"
                    "Пожалуйста, введите сумму от 10 до 100000 ₽:",
                    reply_markup=reply_keyboard
                )
                return
            
            # Убираем флаг ожидания
            context.user_data.pop('waiting_for_donation_amount', None)
            
            # Обрабатываем платеж
            await self._handle_donation_payment_message(update, context, db_user, amount)
            
        except ValueError:
            reply_keyboard = self._get_reply_keyboard()
            await update.message.reply_text(
                "❌ Неверный формат суммы.\n\n"
                "Пожалуйста, введите число (например: 150 или 2500):",
                reply_markup=reply_keyboard
            )
        except Exception as e:
            logger.error(f"Error handling donation amount input: {e}", exc_info=True)
            reply_keyboard = self._get_reply_keyboard()
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке суммы. Попробуйте еще раз или выберите сумму из меню.",
                reply_markup=reply_keyboard
            )
            context.user_data.pop('waiting_for_donation_amount', None)
    
    async def _handle_donation_payment_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User, amount: int):
        """Обработка оплаты доната (вызывается из текстового сообщения)"""
        db = get_db_session()
        try:
            # Генерируем платежную ссылку через Flask сервер
            payment_data = {
                'user_id': db_user.id,
                'amount': amount,
                'description': f'Пожертвование на поддержку VPN сервера от {db_user.nickname or db_user.first_name or db_user.username or f"user_{db_user.telegram_id}"}',
                'payment_type': 'donation'
            }
            
            try:
                # Вызываем Flask сервер для генерации платежной ссылки (с retry)
                response = await self._make_http_request_with_retry(
                    'POST',
                    f"{WEB_SERVER_URL}/generate_payment_uri",
                    json=payment_data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    payment_url = result.get('payment_url')
                    payment_label = result.get('payment_label')
                    
                    text = (
                        f"💚 Пожертвование на поддержку проекта\n\n"
                        f"Сумма: {amount} ₽\n"
                        f"➕ Комиссия (2%): {result.get('commission', 0):.2f} ₽\n"
                        f"💰 Итого к оплате: {result.get('amount_with_commission', amount):.2f} ₽\n\n"
                        f"Спасибо за вашу поддержку! 🙏\n\n"
                        f"Нажмите на кнопку ниже, чтобы перейти к оплате:"
                    )
                    
                    keyboard = [
                        [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
                        [InlineKeyboardButton("✅ Проверить баланс", callback_data="check_payment_balance")],
                        [InlineKeyboardButton("◀️ Назад к выбору суммы", callback_data="pay_vpn")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await update.message.reply_text(text=text, reply_markup=reply_markup)
                else:
                    logger.error(f"Failed to generate payment URL: {response.status_code}, {response.text}")
                    reply_keyboard = self._get_reply_keyboard()
                    await update.message.reply_text(
                        "❌ Ошибка при создании платежной ссылки. Попробуйте позже или обратитесь к администратору.",
                        reply_markup=reply_keyboard
                    )
            except requests.exceptions.RequestException as e:
                logger.error(f"Error connecting to payment server: {e}")
                reply_keyboard = self._get_reply_keyboard()
                await update.message.reply_text(
                    "❌ Сервис оплаты временно недоступен. Попробуйте позже или обратитесь к администратору.",
                    reply_markup=reply_keyboard
                )
        finally:
            db.close()
    
    async def _show_inactive_user_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Показ меню для неактивных пользователей"""
        # Проверяем, был ли запрос отклонен (activation_requested = False после отклонения)
        # Кнопка "Запросить активацию" показывается только если:
        # - Запрос еще не был отправлен (activation_requested = False или None)
        # - Или запрос был отправлен, но еще не обработан (activation_requested = True)
        # Кнопка НЕ показывается только если запрос был явно отклонен (activation_requested = False и activation_requested_at = None после отклонения)
        
        # Если activation_requested = False и activation_requested_at = None - это новый пользователь или после удаления
        # Если activation_requested = True - запрос отправлен, ждем ответа
        # Если activation_requested = False и activation_requested_at != None - запрос был отклонен (не показываем кнопку)
        
        show_activation_button = True
        if db_user.activation_requested is False and db_user.activation_requested_at is not None:
            # Запрос был отклонен - не показываем кнопку
            show_activation_button = False
        
        text = (
            "⚠️ Ваш аккаунт неактивен\n\n"
            "Выберите действие:\n"
            "• 💳 Купить доступ - приобрести VPN ключи"
        )
        
        if db_user.activation_requested:
            text += "\n• ⏳ Запрос активации отправлен - ожидайте ответа администратора"
        elif show_activation_button:
            text += "\n• 🔓 Активировать аккаунт - запросить активацию у администратора"
        
        text += "\n• 📱 Предоставить телефон - для автоверификации"
        
        keyboard = [
            [InlineKeyboardButton("💳 Купить доступ", callback_data="purchase_menu")],
        ]
        
        if db_user.activation_requested:
            # Запрос уже отправлен - показываем только кнопку "Назад"
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_inactive_menu")])
        elif show_activation_button:
            # Показываем кнопку запроса активации
            keyboard.append([InlineKeyboardButton("🔓 Запросить активацию", callback_data="request_activation")])
        
        # Добавляем кнопку для предоставления телефона
        keyboard.append([InlineKeyboardButton("📱 Предоставить телефон", callback_data="provide_phone")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        reply_keyboard = self._get_reply_keyboard()

        # Проверяем, откуда вызывается (callback или message)
        if update.callback_query:
            await self._safe_edit_message_text(update.callback_query, text=text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text=text, reply_markup=reply_markup)
            # Показываем постоянную клавиатуру с кнопкой меню
            await update.message.reply_text(
                "Используйте кнопку ниже для быстрого доступа к меню:",
                reply_markup=reply_keyboard
            )
    
    async def _handle_request_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Обработка запроса активации аккаунта с автоверификацией"""
        query = update.callback_query
        await query.answer()
        
        db = get_db_session()
        try:
            logger.info(f"Activation request from user ID={db_user.id}, telegram_id={db_user.telegram_id}, phone={db_user.phone_number}, username={db_user.username}")
            
            # Проверяем совпадение по одному из параметров: telegram_id, phone_number или username
            found_user = None
            
            # Проверка по telegram_id (ищем активного пользователя с таким же telegram_id, но другим ID)
            if db_user.telegram_id:
                found_user = db.query(User).filter(
                    User.telegram_id == db_user.telegram_id,
                    User.id != db_user.id,  # Исключаем текущего пользователя
                    User.is_active == True,
                    User.is_deleted == False
                ).first()
                if found_user:
                    logger.info(f"Found active user by telegram_id: ID={found_user.id}")
            
            # Проверка по phone_number (если не нашли по telegram_id)
            if not found_user and db_user.phone_number:
                normalized_phone = contacts_manager._normalize_phone(db_user.phone_number)
                found_user = db.query(User).filter(
                    User.phone_number == normalized_phone,
                    User.id != db_user.id,
                    User.is_active == True,
                    User.is_deleted == False
                ).first()
                if found_user:
                    logger.info(f"Found active user by phone: ID={found_user.id}, phone={found_user.phone_number}")
            
            # Дополнительная проверка: ищем активных пользователей без telegram_id (созданных через веб-интерфейс)
            # и проверяем, может ли текущий пользователь быть связан с ними
            if not found_user:
                # Ищем всех активных пользователей без telegram_id
                active_users_without_telegram = db.query(User).filter(
                    User.telegram_id.is_(None),
                    User.is_active == True,
                    User.is_deleted == False
                ).all()
                logger.info(f"Found {len(active_users_without_telegram)} active users without telegram_id")
                
                # Если у текущего пользователя есть телефон, проверяем совпадение
                if db_user.phone_number:
                    normalized_phone = contacts_manager._normalize_phone(db_user.phone_number)
                    for user in active_users_without_telegram:
                        if user.phone_number and contacts_manager._normalize_phone(user.phone_number) == normalized_phone:
                            found_user = user
                            logger.info(f"Found active user by phone (without telegram_id): ID={found_user.id}, phone={found_user.phone_number}")
                            break
            
            # Проверка по username (если не нашли по предыдущим параметрам)
            if not found_user and db_user.username:
                username_normalized = db_user.username.lstrip('@').lower()
                # Получаем всех активных пользователей с username и сравниваем в Python
                active_users_with_username = db.query(User).filter(
                    User.username.isnot(None),
                    User.id != db_user.id,
                    User.is_active == True,
                    User.is_deleted == False
                ).all()
                
                for user in active_users_with_username:
                    if user.username and user.username.lstrip('@').lower() == username_normalized:
                        found_user = user
                        break
            
            # Если найден активный пользователь в базе - автоверификация
            if found_user:
                # Активируем текущего пользователя
                db_user.is_active = True
                db_user.max_keys = found_user.max_keys  # Копируем max_keys из найденного пользователя
                db_user.activation_requested = False
                db_user.activation_requested_at = None
                
                # Обновляем данные пользователя из найденного, если они отсутствуют
                if not db_user.phone_number and found_user.phone_number:
                    db_user.phone_number = found_user.phone_number
                if not db_user.username and found_user.username:
                    db_user.username = found_user.username
                if not db_user.first_name and found_user.first_name:
                    db_user.first_name = found_user.first_name
                if not db_user.last_name and found_user.last_name:
                    db_user.last_name = found_user.last_name
                if not db_user.nickname and found_user.nickname:
                    db_user.nickname = found_user.nickname
                
                db.commit()
                
                # Отправляем приветственное сообщение
                welcome_text = (
                    "✅ Автоверификация успешна!\n\n"
                    "Вы есть в записной книжке Алексея Морозова, "
                    "и вам положен доступ к VPN бесплатно!\n\n"
                    "Теперь вы можете создавать VPN ключи."
                )
                
                reply_keyboard = self._get_reply_keyboard()
                await self._safe_edit_message_text(query, text=welcome_text)
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text="Используйте кнопку ниже для доступа к меню:",
                    reply_markup=reply_keyboard
                )
                
                # Показываем главное меню
                await self._show_main_menu(update, context, db_user)
                return
            
            # Если не найдено совпадение - отправляем запрос администратору
            db_user.activation_requested = True
            db_user.activation_requested_at = datetime.now()
            db.commit()
            
            text = (
                "🔓 Запрос активации аккаунта\n\n"
                "Ваш запрос на активацию отправлен администратору.\n"
                "После активации вы получите уведомление.\n\n"
                "Вы также можете купить доступ, чтобы получить VPN ключи сразу."
            )
            
            keyboard = [
                [InlineKeyboardButton("💳 Купить доступ", callback_data="purchase_menu")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_inactive_menu")],
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)
            
            # Отправляем уведомление администратору с кнопками
            try:
                display_name = self._get_user_display_name_with_username(db_user)
                # Начальное количество ключей по умолчанию
                default_keys = 1
                admin_text = (
                    f"🔓 Запрос на активацию аккаунта\n\n"
                    f"Пользователь: {display_name}\n"
                    f"Telegram ID: {db_user.telegram_id}\n"
                    f"Телефон: {db_user.phone_number or 'не указан'}\n\n"
                    f"Количество ключей: {default_keys}\n\n"
                    f"ID пользователя в БД: {db_user.id}"
                )
                
                admin_keyboard = [
                    [
                        InlineKeyboardButton("➖ -1", callback_data=f"admin_set_activation_keys:{db_user.id}:-1"),
                        InlineKeyboardButton(f"Ключей: {default_keys}", callback_data="noop"),
                        InlineKeyboardButton("➕ +1", callback_data=f"admin_set_activation_keys:{db_user.id}:+1")
                    ],
                    [
                        InlineKeyboardButton("1", callback_data=f"admin_set_activation_keys:{db_user.id}:1"),
                        InlineKeyboardButton("3", callback_data=f"admin_set_activation_keys:{db_user.id}:3"),
                        InlineKeyboardButton("5", callback_data=f"admin_set_activation_keys:{db_user.id}:5")
                    ],
                    [
                        InlineKeyboardButton("✅ Активировать", callback_data=f"admin_activate_user:{db_user.id}:{default_keys}"),
                        InlineKeyboardButton("❌ Отказать", callback_data=f"admin_reject_user:{db_user.id}")
                    ]
                ]
                admin_reply_markup = InlineKeyboardMarkup(admin_keyboard)
                
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=admin_text,
                    reply_markup=admin_reply_markup
                )
            except Exception as e:
                logger.error(f"Error sending activation request to admin: {e}")
        finally:
            db.close()

    async def _handle_provide_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
        """Обработка запроса на предоставление телефона"""
        query = update.callback_query
        await query.answer()
        
        text = (
            "📱 Предоставьте номер телефона\n\n"
            "Для автоверификации нам нужен ваш номер телефона.\n"
            "Нажмите кнопку ниже, чтобы поделиться контактом."
        )
        
        # Создаем клавиатуру с кнопкой для отправки контакта
        contact_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Поделиться контактом", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        await self._safe_edit_message_text(query, text=text)
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="Нажмите кнопку ниже:",
            reply_markup=contact_keyboard
        )

    async def _show_purchase_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ меню покупки QR-кодов для неавторизованных пользователей"""
        # Получаем текущие значения из user_data или устанавливаем по умолчанию
        months = context.user_data.get('purchase_months', 1)
        codes = context.user_data.get('purchase_codes', 1)
        
        # Ограничиваем значения
        months = max(1, min(months, 12))
        codes = max(1, min(codes, 5))
        
        # Сохраняем в user_data
        context.user_data['purchase_months'] = months
        context.user_data['purchase_codes'] = codes
        
        # Рассчитываем цену
        price_info = price_calculator.calculate_price(codes, months)
        total_price = int(price_info['total'])
        
        # Формируем текст сообщения
        month_word = price_calculator._get_month_word(months)
        code_word = price_calculator._get_code_word(codes)
        
        text = (
            f"💳 Покупка QR-кодов\n\n"
            f"📅 Период подписки: [−] {months} {month_word} [+]\n\n"
            f"📦 Количество кодов: [−] {codes} {code_word} [+]\n\n"
            f"💰 Сумма к оплате: {total_price}₽\n\n"
            f"{price_calculator.format_price_info(codes, months)}"
        )
        
        # Формируем клавиатуру
        keyboard = [
            # Строка с кнопками для месяцев
            [
                InlineKeyboardButton("−", callback_data="purchase_months:-"),
                InlineKeyboardButton(f"📅 {months} {month_word}", callback_data="purchase_info"),
                InlineKeyboardButton("+", callback_data="purchase_months:+")
            ],
            # Строка с кнопками для кодов
            [
                InlineKeyboardButton("−", callback_data="purchase_codes:-"),
                InlineKeyboardButton(f"📦 {codes} {code_word}", callback_data="purchase_info"),
                InlineKeyboardButton("+", callback_data="purchase_codes:+")
            ],
            # Кнопка оплаты
            [InlineKeyboardButton(f"💳 Оплатить {total_price}₽", callback_data="purchase_pay")],
            # Кнопка назад
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_inactive_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        reply_keyboard = self._get_reply_keyboard()
        
        # Проверяем, откуда вызывается (callback или message)
        if update.callback_query:
            await self._safe_edit_message_text(update.callback_query, text=text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text=text, reply_markup=reply_markup)
            # Показываем постоянную клавиатуру с кнопкой меню
            await update.message.reply_text(
                "Используйте кнопку ниже для быстрого доступа к меню:",
                reply_markup=reply_keyboard
            )
    
    async def _handle_purchase_months(self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
        """Обработка изменения количества месяцев"""
        query = update.callback_query
        await query.answer()
        
        current_months = context.user_data.get('purchase_months', 1)
        
        if action == "+":
            current_months = min(current_months + 1, 12)
        elif action == "-":
            current_months = max(current_months - 1, 1)
        
        context.user_data['purchase_months'] = current_months
        
        # Показываем обновленное меню
        await self._show_purchase_menu(update, context)
    
    async def _handle_purchase_codes(self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
        """Обработка изменения количества кодов"""
        query = update.callback_query
        await query.answer()
        
        current_codes = context.user_data.get('purchase_codes', 1)
        
        if action == "+":
            current_codes = min(current_codes + 1, 5)
        elif action == "-":
            current_codes = max(current_codes - 1, 1)
        
        context.user_data['purchase_codes'] = current_codes
        
        # Показываем обновленное меню
        await self._show_purchase_menu(update, context)
    
    async def _handle_purchase_pay(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка перехода к оплате"""
        query = update.callback_query
        user = update.effective_user
        
        # Получаем параметры покупки
        months = context.user_data.get('purchase_months', 1)
        codes = context.user_data.get('purchase_codes', 1)
        
        # Рассчитываем цену
        price_info = price_calculator.calculate_price(codes, months)
        total_price = int(price_info['total'])
        
        # Создаем или находим пользователя в БД (может быть неавторизованным)
        db = get_db_session()
        try:
            db_user = db.query(User).filter(User.telegram_id == user.id).first()
            
            if not db_user:
                # Создаем временного пользователя для платежа (НЕ активируем до успешной оплаты)
                db_user = User(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name or "Неавторизованный",
                    last_name=user.last_name,
                    is_active=False,  # НЕ активен до успешной оплаты
                    max_keys=0  # Лимит ключей будет установлен после успешной оплаты через webhook
                )
                db.add(db_user)
                db.commit()
                db.refresh(db_user)
            
            # Генерируем платежную ссылку
            subscription_days = months * 30  # Приблизительно
            
            payment_data = {
                'user_id': db_user.id,
                'amount': total_price,
                'description': f'Покупка {codes} QR-код(ов) на {months} месяц(ев)',
                'payment_type': 'qr_subscription',
                'qr_code_count': codes,
                'subscription_period_days': subscription_days
            }
            
            try:
                # Вызываем Flask сервер для генерации платежной ссылки (с retry)
                response = await self._make_http_request_with_retry(
                    'POST',
                    f"{WEB_SERVER_URL}/generate_payment_uri",
                    json=payment_data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    payment_url = result.get('payment_url')
                    payment_label = result.get('payment_label')
                    
                    # Сохраняем параметры покупки в user_data для дальнейшего использования
                    context.user_data['purchase_payment_label'] = payment_label
                    context.user_data['purchase_months'] = months
                    context.user_data['purchase_codes'] = codes
                    
                    month_word = price_calculator._get_month_word(months)
                    code_word = price_calculator._get_code_word(codes)
                    
                    text = (
                        f"💳 Оплата QR-кодов\n\n"
                        f"📦 Количество кодов: {codes} {code_word}\n"
                        f"📅 Период подписки: {months} {month_word}\n"
                        f"💰 Сумма к оплате: {total_price}₽\n\n"
                        f"После успешной оплаты вы получите QR-код{'и' if codes > 1 else ''} для настройки VPN.\n\n"
                        f"Нажмите на кнопку ниже, чтобы перейти к оплате:"
                    )
                    
                    keyboard = [
                        [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
                        [InlineKeyboardButton("✅ Проверить баланс", callback_data="check_payment_balance")],
                        [InlineKeyboardButton("◀️ Назад к выбору", callback_data="purchase_menu")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)
                else:
                    logger.error(f"Failed to generate payment URL: {response.status_code}, {response.text}")
                    await query.message.reply_text(
                        "❌ Ошибка при создании платежной ссылки. Попробуйте позже или обратитесь к администратору."
                    )
            except requests.exceptions.RequestException as e:
                logger.error(f"Error connecting to payment server: {e}")
                await query.message.reply_text(
                    "❌ Сервис оплаты временно недоступен. Попробуйте позже или обратитесь к администратору."
                )
        finally:
            db.close()
    
    async def _handle_admin_set_activation_keys(self, update: Update, context: ContextTypes.DEFAULT_TYPE, admin_user: User, target_user_id: int, change: str):
        """Изменение количества ключей при активации пользователя"""
        query = update.callback_query
        await query.answer()
        
        db = get_db_session()
        try:
            target_user = db.query(User).filter(User.id == target_user_id).first()
            if not target_user:
                await query.answer("❌ Пользователь не найден.", show_alert=True)
                return
            
            # Получаем текущее количество ключей из callback_data кнопки "Активировать"
            # Ищем в текущем сообщении кнопку активации, чтобы получить текущее значение
            current_keys = 1  # По умолчанию
            
            # Парсим изменение
            if change.startswith("+") or change.startswith("-"):
                # Изменение на +1 или -1
                # Нужно найти текущее значение из сообщения
                message_text = query.message.text
                # Ищем строку "Количество ключей: X"
                match = re.search(r'Количество ключей: (\d+)', message_text)
                if match:
                    current_keys = int(match.group(1))
                
                if change == "+1":
                    new_keys = current_keys + 1
                elif change == "-1":
                    new_keys = max(1, current_keys - 1)  # Минимум 1 ключ
                else:
                    new_keys = current_keys
            else:
                # Прямое значение (1, 3, 5)
                new_keys = int(change)
            
            # Обновляем сообщение с новым количеством ключей
            display_name = self._get_user_display_name_with_username(target_user)
            admin_text = (
                f"🔓 Запрос на активацию аккаунта\n\n"
                f"Пользователь: {display_name}\n"
                f"Telegram ID: {target_user.telegram_id}\n"
                f"Телефон: {target_user.phone_number or 'не указан'}\n\n"
                f"Количество ключей: {new_keys}\n\n"
                f"ID пользователя в БД: {target_user.id}"
            )
            
            admin_keyboard = [
                [
                    InlineKeyboardButton("➖ -1", callback_data=f"admin_set_activation_keys:{target_user_id}:-1"),
                    InlineKeyboardButton(f"Ключей: {new_keys}", callback_data="noop"),
                    InlineKeyboardButton("➕ +1", callback_data=f"admin_set_activation_keys:{target_user_id}:+1")
                ],
                [
                    InlineKeyboardButton("1", callback_data=f"admin_set_activation_keys:{target_user_id}:1"),
                    InlineKeyboardButton("3", callback_data=f"admin_set_activation_keys:{target_user_id}:3"),
                    InlineKeyboardButton("5", callback_data=f"admin_set_activation_keys:{target_user_id}:5")
                ],
                [
                    InlineKeyboardButton("✅ Активировать", callback_data=f"admin_activate_user:{target_user_id}:{new_keys}"),
                    InlineKeyboardButton("❌ Отказать", callback_data=f"admin_reject_user:{target_user_id}")
                ]
            ]
            admin_reply_markup = InlineKeyboardMarkup(admin_keyboard)
            
            await self._safe_edit_message_text(query, text=admin_text, reply_markup=admin_reply_markup)
        finally:
            db.close()
    
    async def _handle_admin_activate_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, admin_user: User, target_user_id: int, keys_count: int = 1):
        """Активация пользователя администратором с указанным количеством ключей"""
        query = update.callback_query
        await query.answer()
        
        db = get_db_session()
        try:
            target_user = db.query(User).filter(User.id == target_user_id).first()
            if not target_user:
                await query.message.reply_text("❌ Пользователь не найден.")
                return
            
            # Активируем пользователя с указанным количеством ключей
            target_user.is_active = True
            target_user.activation_requested = False
            target_user.activation_requested_at = None
            target_user.max_keys = keys_count  # Устанавливаем выбранное количество ключей
            db.commit()
            
            # Отправляем уведомление пользователю
            if target_user.telegram_id:
                try:
                    keys_text = "ключ" if keys_count == 1 else "ключа" if keys_count < 5 else "ключей"
                    reply_keyboard = self._get_reply_keyboard()
                    await context.bot.send_message(
                        chat_id=target_user.telegram_id,
                        text=f"✅ Ваш аккаунт активирован! Теперь вы можете использовать бота.\n\n"
                             f"Вам доступно создание {keys_count} {keys_text}.",
                        reply_markup=reply_keyboard
                    )
                except Exception as e:
                    logger.error(f"Error sending activation notification: {e}")
            
            # Обновляем сообщение администратору
            await self._safe_edit_message_text(
                query,
                text=f"✅ Пользователь {target_user.first_name or 'Без имени'} активирован с {keys_count} ключами!"
            )
        finally:
            db.close()
    
    async def _handle_admin_reject_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, admin_user: User, target_user_id: int):
        """Отказ в активации пользователя администратором"""
        query = update.callback_query
        await query.answer()
        
        db = get_db_session()
        try:
            target_user = db.query(User).filter(User.id == target_user_id).first()
            if not target_user:
                await query.message.reply_text("❌ Пользователь не найден.")
                return
            
            # При отказе устанавливаем activation_requested = False, но оставляем activation_requested_at
            # Это позволит отличить отклоненный запрос от нового пользователя
            # Если activation_requested_at != None, значит запрос был обработан (отклонен)
            if target_user.activation_requested_at is None:
                target_user.activation_requested_at = datetime.now()
            target_user.activation_requested = False
            db.commit()
            
            # Отправляем уведомление пользователю
            if target_user.telegram_id:
                try:
                    reply_keyboard = self._get_reply_keyboard()
                    await context.bot.send_message(
                        chat_id=target_user.telegram_id,
                        text="❌ Ваш запрос на активацию отклонен. Вы можете купить доступ или обратиться к администратору.",
                        reply_markup=reply_keyboard
                    )
                except Exception as e:
                    logger.error(f"Error sending rejection notification: {e}")
            
            # Обновляем сообщение администратору
            await self._safe_edit_message_text(
                query,
                text=f"❌ Запрос на активацию пользователя {target_user.first_name or 'Без имени'} отклонен."
            )
        finally:
            db.close()

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        query = update.callback_query

        text = (
            "ℹ️ Помощь\n\n"
            "Этот бот позволяет управлять VPN ключами для AmneziaWG.\n\n"
            "Основные функции:\n"
            "• 🔐 Создание VPN ключей\n"
            "• 💳 Оплата VPN доступа\n"
            "• 📋 Просмотр ваших ключей\n"
            "• 🗑 Удаление ключей\n\n"
            "Для создания ключа нажмите \"🔐 Получить AmneziaWG ключ\".\n"
            "После создания вы получите файл конфигурации и QR-код для быстрой настройки.\n\n"
            "Если возникли вопросы, обратитесь к администратору."
        )

        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self._safe_edit_message_text(query, text=text, reply_markup=reply_markup)

    def run(self):
        """Запуск бота"""
        # Инициализация БД
        init_db()

        # Создание приложения
        self.app = Application.builder().token(BOT_TOKEN).build()

        # Регистрация обработчиков
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(MessageHandler(filters.CONTACT, self.handle_contact))
        # Обработчик текстовых сообщений ДОЛЖЕН быть после обработчика контактов, но перед callback
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        self.app.add_error_handler(self._application_error_handler)

        # Запуск бота
        logger.info("Bot started")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    bot = VPNBot()
    bot.run()
