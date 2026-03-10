#!/usr/bin/env python3
"""Тест добавления номеров телефона"""
import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from contacts import ContactsManager
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_normalization():
    """Тест нормализации номеров"""
    cm = ContactsManager()
    
    test_cases = [
        '+79933393296',
        '79933393296',
        '89933393296',
        '7993339329',
        '8508768596',
    ]
    
    print("=== Тест нормализации номеров ===")
    for num in test_cases:
        normalized = cm._normalize_phone(num)
        print(f"{num:15} -> {normalized}")
    
    print("\n=== Тест добавления номеров ===")
    
    # Очищаем контакты для теста
    cm.contacts = {}
    cm._save_contacts()
    
    # Добавляем номера в разных форматах
    test_numbers = [
        '+79933393296',
        '79933393296',
        '89933393296',
    ]
    
    for num in test_numbers:
        print(f"\nДобавляем: {num}")
        cm.add_contact(num)
        all_contacts = cm.get_all_contacts()
        print(f"Контакты после добавления: {list(all_contacts.keys())}")
    
    print("\n=== Финальный список контактов ===")
    all_contacts = cm.get_all_contacts()
    for key, value in all_contacts.items():
        print(f"{key}: {value}")
    
    print("\n=== Тест поиска номера ===")
    search_numbers = [
        '+79933393296',
        '79933393296',
        '89933393296',
    ]
    
    for num in search_numbers:
        found = cm.find_by_phone(num)
        print(f"Поиск '{num}': {'НАЙДЕН' if found else 'НЕ НАЙДЕН'}")
        if found:
            print(f"  Данные: {found}")

if __name__ == '__main__':
    test_normalization()

