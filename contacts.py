"""Управление контактами (contacts.json)"""
import json
from pathlib import Path
from typing import Optional, Dict, List
from config import CONTACTS_FILE


class ContactsManager:
    """Менеджер для работы с contacts.json"""

    def __init__(self, contacts_file: Path = CONTACTS_FILE):
        self.contacts_file = contacts_file
        self.contacts_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_contacts()

    def _load_contacts(self) -> Dict:
        """Загрузка контактов из файла"""
        if not self.contacts_file.exists():
            self.contacts = {}
            self._save_contacts()
            return self.contacts

        try:
            with open(self.contacts_file, 'r', encoding='utf-8') as f:
                self.contacts = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            self.contacts = {}
            self._save_contacts()

        return self.contacts

    def _save_contacts(self):
        """Сохранение контактов в файл"""
        with open(self.contacts_file, 'w', encoding='utf-8') as f:
            json.dump(self.contacts, f, ensure_ascii=False, indent=2)

    def find_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        """Поиск контакта по Telegram ID"""
        contacts = self._load_contacts()
        for phone, data in contacts.items():
            if isinstance(data, dict) and data.get('telegram_id') == telegram_id:
                return {'phone': phone, **data}
        return None

    def find_by_username(self, username: str) -> Optional[Dict]:
        """Поиск контакта по username"""
        if not username:
            return None
        username = username.lstrip('@').lower()
        contacts = self._load_contacts()
        for phone, data in contacts.items():
            if isinstance(data, dict) and data.get('username', '').lower() == username:
                return {'phone': phone, **data}
        return None

    def find_by_phone(self, phone_number: str) -> Optional[Dict]:
        """Поиск контакта по номеру телефона"""
        import logging
        logger = logging.getLogger(__name__)
        
        original = phone_number
        phone_number = self._normalize_phone(phone_number)
        logger.debug(f"find_by_phone: original='{original}' -> normalized='{phone_number}'")
        
        contacts = self._load_contacts()
        result = contacts.get(phone_number)
        logger.debug(f"find_by_phone: result={'found' if result else 'not found'}")
        return result

    def _normalize_phone(self, phone: str) -> str:
        """Нормализация номера телефона"""
        if not phone:
            return phone
        
        # Убираем все нецифровые символы кроме +
        cleaned = ''.join(c for c in phone if c.isdigit() or c == '+')
        
        # Если номер начинается с +, проверяем дальше
        if cleaned.startswith('+'):
            # Если номер +7XX... (российский), оставляем как есть
            if cleaned.startswith('+7'):
                return cleaned
            # Если номер +8XX... (возможно ошибка), заменяем +8 на +7
            elif cleaned.startswith('+8'):
                return '+7' + cleaned[2:]
            # Для других + номеров оставляем как есть
            return cleaned
        
        # Если номер без + и начинается с 8, заменяем на +7
        if cleaned.startswith('8'):
            # 89933393296 -> +79933393296
            return '+7' + cleaned[1:]
        
        # Если номер без + и начинается с 7, добавляем +
        if cleaned.startswith('7'):
            # 79933393296 -> +79933393296
            return '+' + cleaned
        
        # Если номер без + и состоит только из цифр (но не начинается с 7 или 8)
        # Добавляем +7 (предполагаем российский номер)
        if cleaned.isdigit():
            return '+7' + cleaned
        
        return cleaned

    def add_contact(self, phone_number: str, telegram_id: Optional[int] = None,
                    username: Optional[str] = None, first_name: Optional[str] = None,
                    last_name: Optional[str] = None):
        """Добавление контакта"""
        import logging
        logger = logging.getLogger(__name__)
        
        original_phone = phone_number
        phone_number = self._normalize_phone(phone_number)
        logger.info(f"add_contact: original='{original_phone}' -> normalized='{phone_number}'")
        
        contacts = self._load_contacts()
        logger.info(f"Current contacts before add: {list(contacts.keys())}")

        contact_data = {
            'telegram_id': telegram_id,
            'username': username,
            'first_name': first_name,
            'last_name': last_name
        }
        # Убираем None значения
        contact_data = {k: v for k, v in contact_data.items() if v is not None}

        # Если контакт уже существует, обновляем данные
        if phone_number in contacts:
            if isinstance(contacts[phone_number], dict):
                contacts[phone_number].update(contact_data)
                logger.info(f"Updated existing contact: {phone_number}")
            else:
                contacts[phone_number] = contact_data
                logger.info(f"Replaced contact with dict: {phone_number}")
        else:
            contacts[phone_number] = contact_data
            logger.info(f"Added new contact: {phone_number}")

        self.contacts = contacts
        self._save_contacts()
        logger.info(f"Saved contacts. Keys after save: {list(self.contacts.keys())}")
        
        # Проверяем, что сохранилось
        verify_contacts = self._load_contacts()
        logger.info(f"Verified contacts after save: {list(verify_contacts.keys())}")

    def is_authorized(self, telegram_id: Optional[int] = None, username: Optional[str] = None,
                     phone_number: Optional[str] = None) -> bool:
        """Проверка авторизации пользователя"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.debug(f"is_authorized called with telegram_id={telegram_id}, username={username}, phone_number={phone_number}")
        
        # Проверка по Telegram ID
        if telegram_id:
            contact = self.find_by_telegram_id(telegram_id)
            if contact:
                logger.debug(f"Authorized by telegram_id: {telegram_id}")
                return True

        # Проверка по username
        if username:
            contact = self.find_by_username(username)
            if contact:
                logger.debug(f"Authorized by username: {username}")
                return True

        # Проверка по номеру телефона
        if phone_number:
            # Нормализуем номер перед проверкой
            normalized = self._normalize_phone(phone_number)
            logger.info(f"is_authorized: Checking phone: original='{phone_number}', normalized='{normalized}'")
            
            # Используем нормализованный номер для поиска
            contact = self.find_by_phone(normalized)
            if contact:
                logger.info(f"is_authorized: Authorized by phone: {normalized}")
                return True
            else:
                # Проверяем все контакты для отладки
                all_contacts = self.get_all_contacts()
                logger.warning(f"is_authorized: Phone {normalized} not found. All contact keys: {list(all_contacts.keys())}")
                
                # Дополнительная проверка: ищем напрямую в словаре контактов
                contacts = self._load_contacts()
                if normalized in contacts:
                    logger.info(f"is_authorized: Found normalized phone {normalized} directly in contacts dict")
                    return True

        logger.debug(f"Authorization failed for telegram_id={telegram_id}, username={username}, phone_number={phone_number}")
        return False

    def get_all_contacts(self) -> Dict:
        """Получение всех контактов"""
        return self._load_contacts()

    def remove_contact(self, phone_number: str):
        """Удаление контакта"""
        phone_number = self._normalize_phone(phone_number)
        contacts = self._load_contacts()
        if phone_number in contacts:
            del contacts[phone_number]
            self.contacts = contacts
            self._save_contacts()


# Глобальный экземпляр менеджера контактов
contacts_manager = ContactsManager()
