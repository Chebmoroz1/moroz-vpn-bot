"""Скрипт миграции contacts.json в базу данных"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from database import init_db, get_db_session, User
from contacts import contacts_manager
from config import DATABASE_PATH, ADMIN_ID

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def migrate_contacts_to_db():
    """Миграция контактов из contacts.json в базу данных"""
    logger.info("Starting migration of contacts.json to database...")
    
    # Инициализируем БД
    init_db()
    
    # Получаем все контакты из contacts.json
    all_contacts = contacts_manager.get_all_contacts()
    
    if not all_contacts:
        logger.info("No contacts found in contacts.json. Nothing to migrate.")
        return
    
    logger.info(f"Found {len(all_contacts)} contacts in contacts.json")
    
    db = get_db_session()
    stats = {
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0
    }
    
    try:
        for phone_number, contact_data in all_contacts.items():
            try:
                # Пропускаем невалидные записи
                if not isinstance(contact_data, dict):
                    logger.warning(f"Skipping invalid contact entry: {phone_number} (not a dict)")
                    stats['skipped'] += 1
                    continue
                
                # Извлекаем данные
                telegram_id = contact_data.get('telegram_id')
                username = contact_data.get('username')
                first_name = contact_data.get('first_name')
                last_name = contact_data.get('last_name')
                
                # Нормализуем номер телефона (используем тот же метод, что и в contacts_manager)
                normalized_phone = contacts_manager._normalize_phone(phone_number)
                
                # Проверяем, существует ли пользователь
                # Сначала ищем по Telegram ID (если есть)
                db_user = None
                if telegram_id:
                    db_user = db.query(User).filter(User.telegram_id == telegram_id).first()
                
                # Если не нашли по Telegram ID, ищем по телефону
                if not db_user and normalized_phone:
                    db_user = db.query(User).filter(User.phone_number == normalized_phone).first()
                
                if db_user:
                    # Обновляем существующего пользователя
                    logger.info(f"Updating user {db_user.id} (telegram_id: {telegram_id}, phone: {normalized_phone})")
                    
                    # Обновляем только те поля, которые не заполнены или если они изменились
                    if telegram_id and not db_user.telegram_id:
                        db_user.telegram_id = telegram_id
                    
                    if normalized_phone and not db_user.phone_number:
                        db_user.phone_number = normalized_phone
                    
                    if username:
                        db_user.username = username
                    
                    if first_name:
                        db_user.first_name = first_name
                    
                    if last_name:
                        db_user.last_name = last_name
                    
                    # Проверяем, является ли администратором
                    if telegram_id == ADMIN_ID:
                        db_user.is_admin = True
                    
                    db.commit()
                    stats['updated'] += 1
                    logger.info(f"Updated user {db_user.id}")
                    
                else:
                    # Создаем нового пользователя
                    logger.info(f"Creating new user (telegram_id: {telegram_id}, phone: {normalized_phone})")
                    
                    # Если есть Telegram ID, пользователь уже авторизован
                    # Если нет - создаем пользователя только с телефоном (для последующей авторизации)
                    is_active = telegram_id is not None
                    
                    db_user = User(
                        telegram_id=telegram_id,  # Может быть None
                        username=username,
                        first_name=first_name or "Неавторизованный",
                        last_name=last_name,
                        phone_number=normalized_phone,
                        is_active=is_active,
                        is_admin=(telegram_id == ADMIN_ID if telegram_id else False),
                        max_keys=1
                    )
                    
                    db.add(db_user)
                    db.commit()
                    db.refresh(db_user)
                    stats['created'] += 1
                    logger.info(f"Created user {db_user.id}")
                    
            except Exception as e:
                logger.error(f"Error migrating contact {phone_number}: {e}", exc_info=True)
                stats['errors'] += 1
                db.rollback()
        
        logger.info(f"Migration completed. Stats: {stats}")
        
        # Проверяем результаты
        total_users = db.query(User).count()
        logger.info(f"Total users in database: {total_users}")
        
    except Exception as e:
        logger.error(f"Error during migration: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
    
    return stats


def verify_migration():
    """Проверка результатов миграции"""
    logger.info("Verifying migration results...")
    
    db = get_db_session()
    try:
        # Получаем все пользователи
        all_users = db.query(User).all()
        
        logger.info(f"Total users in database: {len(all_users)}")
        
        # Проверяем пользователей с телефонами
        users_with_phone = db.query(User).filter(User.phone_number.isnot(None)).count()
        logger.info(f"Users with phone numbers: {users_with_phone}")
        
        # Проверяем пользователей с Telegram ID
        users_with_telegram = db.query(User).filter(User.telegram_id.isnot(None)).count()
        logger.info(f"Users with Telegram ID: {users_with_telegram}")
        
        # Проверяем активных пользователей
        active_users = db.query(User).filter(User.is_active == True).count()
        logger.info(f"Active users: {active_users}")
        
        # Проверяем администраторов
        admins = db.query(User).filter(User.is_admin == True).count()
        logger.info(f"Administrators: {admins}")
        
    finally:
        db.close()


if __name__ == '__main__':
    print("=" * 60)
    print("Migration of contacts.json to database")
    print("=" * 60)
    print()
    
    try:
        stats = migrate_contacts_to_db()
        
        print()
        print("Migration completed!")
        print(f"  Created: {stats['created']}")
        print(f"  Updated: {stats['updated']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Errors: {stats['errors']}")
        print()
        
        verify_migration()
        
        print()
        print("=" * 60)
        print("Next steps:")
        print("1. Review the migration results above")
        print("2. Test the bot to ensure authorization works correctly")
        print("3. After verifying, you can safely delete contacts.json (it will be kept as backup)")
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        print()
        print("=" * 60)
        print("❌ Migration failed! See logs above for details.")
        print("=" * 60)
        exit(1)

