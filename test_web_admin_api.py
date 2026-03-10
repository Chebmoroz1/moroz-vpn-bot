#!/usr/bin/env python3
"""
Скрипт для тестирования API веб-панели администрирования VPN Bot
"""
import sys
import os
import requests
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, str(Path(__file__).parent))

from config import ADMIN_ID, WEB_SERVER_URL
from database import SessionLocal, User

# URL API (по умолчанию localhost, можно переопределить через переменную окружения)
API_BASE_URL = os.getenv("WEB_ADMIN_API_URL", "http://localhost:8889")
API_URL = f"{API_BASE_URL}/api"

# Цвета для вывода
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

# Счетчики тестов
test_results = {
    "passed": 0,
    "failed": 0,
    "skipped": 0
}

def print_test(name: str):
    """Вывод названия теста"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}▶ {name}{Colors.RESET}")

def print_success(message: str):
    """Вывод успешного результата"""
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")
    test_results["passed"] += 1

def print_error(message: str):
    """Вывод ошибки"""
    print(f"{Colors.RED}✗ {message}{Colors.RESET}")
    test_results["failed"] += 1

def print_warning(message: str):
    """Вывод предупреждения"""
    print(f"{Colors.YELLOW}⚠ {message}{Colors.RESET}")
    test_results["skipped"] += 1

def print_info(message: str):
    """Вывод информации"""
    print(f"  {message}")

# Глобальная переменная для токена
admin_token: Optional[str] = None

def test_api_health():
    """Тест 1: Проверка доступности API"""
    print_test("Проверка доступности API")
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        if response.status_code == 200:
            print_success("API доступен")
            print_info(f"Ответ: {response.json() if response.headers.get('content-type', '').startswith('application/json') else 'HTML'}")
            return True
        else:
            print_error(f"API вернул статус {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error(f"Не удалось подключиться к API по адресу {API_BASE_URL}")
        print_info("Убедитесь, что FastAPI backend запущен (порт 8889)")
        return False
    except Exception as e:
        print_error(f"Ошибка при проверке API: {e}")
        return False

def test_generate_token():
    """Тест 2: Генерация токена администратора"""
    global admin_token
    print_test("Генерация токена администратора")
    
    # Получаем telegram_id администратора из БД
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.telegram_id == ADMIN_ID).first()
        if not admin_user:
            print_warning(f"Администратор с telegram_id={ADMIN_ID} не найден в БД")
            print_info("Попытка генерации токена напрямую...")
            telegram_id = ADMIN_ID
        else:
            telegram_id = admin_user.telegram_id
            print_info(f"Найден администратор: {admin_user.first_name} (ID: {telegram_id})")
    finally:
        db.close()
    
    try:
        response = requests.post(
            f"{API_URL}/auth/token",
            json={"telegram_id": telegram_id},
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            admin_token = data.get("token")
            expires_at = data.get("expires_at")
            print_success(f"Токен успешно сгенерирован")
            print_info(f"Токен: {admin_token[:20]}...")
            print_info(f"Истекает: {expires_at}")
            return True
        elif response.status_code == 403:
            print_error("Доступ запрещен. Убедитесь, что пользователь является администратором.")
            return False
        else:
            print_error(f"Ошибка генерации токена: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print_error(f"Ошибка при генерации токена: {e}")
        return False

def test_verify_token():
    """Тест 3: Проверка токена"""
    print_test("Проверка токена")
    
    if not admin_token:
        print_warning("Токен не сгенерирован, пропускаем тест")
        return False
    
    try:
        response = requests.get(
            f"{API_URL}/auth/verify",
            params={"token": admin_token},
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Токен валиден")
            print_info(f"Администратор: {data.get('admin', {}).get('first_name', 'N/A')}")
            return True
        else:
            print_error(f"Токен невалиден: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print_error(f"Ошибка при проверке токена: {e}")
        return False

def test_get_users():
    """Тест 4: Получение списка пользователей"""
    print_test("Получение списка пользователей")
    
    if not admin_token:
        print_warning("Токен не сгенерирован, пропускаем тест")
        return False
    
    try:
        response = requests.get(
            f"{API_URL}/users",
            params={"token": admin_token, "skip": 0, "limit": 10},
            timeout=5
        )
        
        if response.status_code == 200:
            users = response.json()
            print_success(f"Получено пользователей: {len(users)}")
            if users:
                print_info(f"Первый пользователь: {users[0].get('first_name', 'N/A')} (ID: {users[0].get('id')})")
            return True
        else:
            print_error(f"Ошибка получения пользователей: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print_error(f"Ошибка при получении пользователей: {e}")
        return False

def test_get_user_by_id():
    """Тест 5: Получение пользователя по ID"""
    print_test("Получение пользователя по ID")
    
    if not admin_token:
        print_warning("Токен не сгенерирован, пропускаем тест")
        return False
    
    # Сначала получаем список пользователей
    try:
        response = requests.get(
            f"{API_URL}/users",
            params={"token": admin_token, "limit": 1},
            timeout=5
        )
        
        if response.status_code == 200:
            users = response.json()
            if not users:
                print_warning("Нет пользователей для тестирования")
                return False
            
            user_id = users[0].get("id")
            
            # Получаем пользователя по ID
            response = requests.get(
                f"{API_URL}/users/{user_id}",
                params={"token": admin_token},
                timeout=5
            )
            
            if response.status_code == 200:
                user = response.json()
                print_success(f"Пользователь получен: {user.get('first_name', 'N/A')} (ID: {user.get('id')})")
                return True
            else:
                print_error(f"Ошибка получения пользователя: {response.status_code} - {response.text}")
                return False
        else:
            print_error(f"Не удалось получить список пользователей: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Ошибка при получении пользователя: {e}")
        return False

def test_get_keys():
    """Тест 6: Получение списка ключей"""
    print_test("Получение списка ключей")
    
    if not admin_token:
        print_warning("Токен не сгенерирован, пропускаем тест")
        return False
    
    try:
        response = requests.get(
            f"{API_URL}/keys",
            params={"token": admin_token, "limit": 10},
            timeout=5
        )
        
        if response.status_code == 200:
            keys = response.json()
            print_success(f"Получено ключей: {len(keys)}")
            if keys:
                print_info(f"Первый ключ: {keys[0].get('key_name', 'N/A')} (ID: {keys[0].get('id')})")
            return True
        else:
            print_error(f"Ошибка получения ключей: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print_error(f"Ошибка при получении ключей: {e}")
        return False

def test_get_traffic_stats():
    """Тест 7: Получение статистики трафика"""
    print_test("Получение статистики трафика")
    
    if not admin_token:
        print_warning("Токен не сгенерирован, пропускаем тест")
        return False
    
    try:
        response = requests.get(
            f"{API_URL}/traffic",
            params={"token": admin_token},
            timeout=10  # Может занять больше времени из-за синхронизации
        )
        
        if response.status_code == 200:
            stats = response.json()
            print_success(f"Получено записей статистики: {len(stats)}")
            if stats:
                total_traffic = sum(s.get("bytes_total", 0) for s in stats)
                print_info(f"Общий трафик: {total_traffic / (1024**3):.2f} GB")
            return True
        else:
            print_error(f"Ошибка получения статистики: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print_error(f"Ошибка при получении статистики: {e}")
        return False

def test_create_user():
    """Тест 8: Создание нового пользователя"""
    print_test("Создание нового пользователя")
    
    if not admin_token:
        print_warning("Токен не сгенерирован, пропускаем тест")
        return False
    
    # Создаем тестового пользователя
    test_user_data = {
        "phone_number": "+79999999999",
        "first_name": "Test",
        "last_name": "User",
        "nickname": "test_user",
        "is_active": True,
        "max_keys": 1
    }
    
    try:
        response = requests.post(
            f"{API_URL}/users",
            params={"token": admin_token},
            json=test_user_data,
            timeout=5
        )
        
        if response.status_code == 200:
            user = response.json()
            print_success(f"Пользователь создан: {user.get('first_name')} (ID: {user.get('id')})")
            return user.get("id")
        elif response.status_code == 400 and "already exists" in response.text:
            print_warning("Пользователь уже существует (это нормально)")
            return None
        else:
            print_error(f"Ошибка создания пользователя: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print_error(f"Ошибка при создании пользователя: {e}")
        return None

def test_update_user(user_id: Optional[int]):
    """Тест 9: Обновление пользователя"""
    print_test("Обновление пользователя")
    
    if not admin_token:
        print_warning("Токен не сгенерирован, пропускаем тест")
        return False
    
    if not user_id:
        print_warning("Нет пользователя для обновления, пропускаем тест")
        return False
    
    update_data = {
        "nickname": "updated_test_user",
        "max_keys": 2
    }
    
    try:
        response = requests.put(
            f"{API_URL}/users/{user_id}",
            params={"token": admin_token},
            json=update_data,
            timeout=5
        )
        
        if response.status_code == 200:
            user = response.json()
            print_success(f"Пользователь обновлен: nickname={user.get('nickname')}, max_keys={user.get('max_keys')}")
            return True
        else:
            print_error(f"Ошибка обновления пользователя: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print_error(f"Ошибка при обновлении пользователя: {e}")
        return False

def test_export_users_csv():
    """Тест 10: Экспорт пользователей в CSV"""
    print_test("Экспорт пользователей в CSV")
    
    if not admin_token:
        print_warning("Токен не сгенерирован, пропускаем тест")
        return False
    
    try:
        response = requests.get(
            f"{API_URL}/users/export/csv",
            params={"token": admin_token},
            timeout=10
        )
        
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if "text/csv" in content_type or "application/csv" in content_type:
                csv_content = response.text
                lines = csv_content.split("\n")
                print_success(f"CSV экспортирован: {len(lines)} строк")
                print_info(f"Размер файла: {len(csv_content)} байт")
                return True
            else:
                print_error(f"Неверный content-type: {content_type}")
                return False
        else:
            print_error(f"Ошибка экспорта CSV: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print_error(f"Ошибка при экспорте CSV: {e}")
        return False

def test_key_operations():
    """Тест 11: Операции с ключами (активация/деактивация)"""
    print_test("Операции с ключами")
    
    if not admin_token:
        print_warning("Токен не сгенерирован, пропускаем тест")
        return False
    
    # Получаем список ключей
    try:
        response = requests.get(
            f"{API_URL}/keys",
            params={"token": admin_token, "limit": 1},
            timeout=5
        )
        
        if response.status_code == 200:
            keys = response.json()
            if not keys:
                print_warning("Нет ключей для тестирования")
                return False
            
            key_id = keys[0].get("id")
            is_active = keys[0].get("is_active")
            
            # Тестируем деактивацию/активацию
            if is_active:
                # Деактивируем
                response = requests.put(
                    f"{API_URL}/keys/{key_id}/deactivate",
                    params={"token": admin_token},
                    timeout=5
                )
                if response.status_code == 200:
                    print_success("Ключ деактивирован")
                else:
                    print_error(f"Ошибка деактивации: {response.status_code}")
                    return False
                
                # Активируем обратно
                response = requests.put(
                    f"{API_URL}/keys/{key_id}/activate",
                    params={"token": admin_token},
                    timeout=5
                )
                if response.status_code == 200:
                    print_success("Ключ активирован")
                    return True
                else:
                    print_error(f"Ошибка активации: {response.status_code}")
                    return False
            else:
                # Активируем
                response = requests.put(
                    f"{API_URL}/keys/{key_id}/activate",
                    params={"token": admin_token},
                    timeout=5
                )
                if response.status_code == 200:
                    print_success("Ключ активирован")
                    return True
                else:
                    print_error(f"Ошибка активации: {response.status_code}")
                    return False
        else:
            print_error(f"Не удалось получить список ключей: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Ошибка при операциях с ключами: {e}")
        return False

def test_unauthorized_access():
    """Тест 12: Проверка защиты от неавторизованного доступа"""
    print_test("Проверка защиты от неавторизованного доступа")
    
    try:
        # Пытаемся получить пользователей без токена
        response = requests.get(
            f"{API_URL}/users",
            timeout=5
        )
        
        if response.status_code == 401:
            print_success("Доступ без токена запрещен (401)")
            return True
        else:
            print_error(f"Ожидался статус 401, получен {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Ошибка при проверке защиты: {e}")
        return False

def print_summary():
    """Вывод итогов тестирования"""
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}ИТОГИ ТЕСТИРОВАНИЯ{Colors.RESET}")
    print(f"{'='*60}")
    print(f"{Colors.GREEN}✓ Пройдено: {test_results['passed']}{Colors.RESET}")
    print(f"{Colors.RED}✗ Провалено: {test_results['failed']}{Colors.RESET}")
    print(f"{Colors.YELLOW}⚠ Пропущено: {test_results['skipped']}{Colors.RESET}")
    
    total = sum(test_results.values())
    if total > 0:
        success_rate = (test_results['passed'] / total) * 100
        print(f"\nУспешность: {success_rate:.1f}%")
    
    print(f"{'='*60}\n")

def main():
    """Главная функция"""
    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("="*60)
    print("ТЕСТИРОВАНИЕ API ВЕБ-ПАНЕЛИ АДМИНИСТРИРОВАНИЯ VPN BOT")
    print("="*60)
    print(f"{Colors.RESET}")
    print(f"API URL: {API_BASE_URL}")
    print(f"ADMIN_ID: {ADMIN_ID}")
    print()
    
    # Запускаем тесты
    test_api_health()
    test_generate_token()
    test_verify_token()
    test_unauthorized_access()
    test_get_users()
    test_get_user_by_id()
    test_get_keys()
    test_get_traffic_stats()
    test_user_id = test_create_user()
    test_update_user(test_user_id)
    test_export_users_csv()
    test_key_operations()
    
    # Выводим итоги
    print_summary()
    
    # Возвращаем код выхода
    if test_results['failed'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()



