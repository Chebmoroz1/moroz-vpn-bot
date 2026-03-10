"""Тестовый скрипт для проверки подключения к серверу"""
import logging
from vpn_manager import vpn_manager

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

def test_ssh_connection():
    """Тест SSH подключения"""
    print("🔍 Проверка SSH подключения...")
    
    # Простой тест - проверка доступности сервера
    stdout, stderr, exit_code = vpn_manager._ssh_exec("echo 'SSH connection OK'")
    
    if exit_code == 0:
        print(f"✅ SSH подключение работает!")
        print(f"Ответ сервера: {stdout.strip()}")
        return True
    else:
        print(f"❌ SSH подключение не работает!")
        print(f"Ошибка: {stderr}")
        return False

def test_docker_container():
    """Тест Docker контейнера"""
    print("\n🔍 Проверка Docker контейнера...")
    
    stdout, stderr, exit_code = vpn_manager._ssh_exec(
        f"docker ps --filter name={vpn_manager.docker_container} --format '{{{{.Names}}}}'",
        docker_exec=False
    )
    
    if exit_code == 0 and vpn_manager.docker_container in stdout:
        print(f"✅ Docker контейнер {vpn_manager.docker_container} запущен!")
        return True
    else:
        print(f"❌ Docker контейнер {vpn_manager.docker_container} не найден!")
        print(f"Ошибка: {stderr}")
        return False

def test_wg_interface():
    """Тест WireGuard интерфейса"""
    print("\n🔍 Проверка WireGuard интерфейса...")
    
    stdout, stderr, exit_code = vpn_manager._ssh_exec(
        f"wg show {vpn_manager.vpn_interface}",
        docker_exec=True
    )
    
    if exit_code == 0:
        print(f"✅ WireGuard интерфейс {vpn_manager.vpn_interface} работает!")
        print(f"Информация об интерфейсе:\n{stdout[:200]}...")
        return True
    else:
        print(f"❌ WireGuard интерфейс {vpn_manager.vpn_interface} не работает!")
        print(f"Ошибка: {stderr}")
        return False

def test_server_public_key():
    """Тест получения публичного ключа сервера"""
    print("\n🔍 Проверка получения публичного ключа сервера...")
    
    try:
        public_key = vpn_manager.get_server_public_key()
        if public_key:
            print(f"✅ Публичный ключ сервера получен!")
            print(f"Ключ: {public_key[:50]}...")
            return True
        else:
            print(f"❌ Не удалось получить публичный ключ сервера!")
            return False
    except Exception as e:
        print(f"❌ Ошибка при получении публичного ключа: {e}")
        return False

def test_available_ips():
    """Тест получения доступных IP"""
    print("\n🔍 Проверка получения доступных IP адресов...")
    
    try:
        ip = vpn_manager.get_next_available_ip()
        if ip:
            print(f"✅ Доступный IP адрес: {ip}")
            return True
        else:
            print(f"❌ Нет доступных IP адресов!")
            return False
    except Exception as e:
        print(f"❌ Ошибка при получении IP: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Тестирование подключения к VPN серверу\n")
    
    results = []
    results.append(("SSH подключение", test_ssh_connection()))
    results.append(("Docker контейнер", test_docker_container()))
    results.append(("WireGuard интерфейс", test_wg_interface()))
    results.append(("Публичный ключ сервера", test_server_public_key()))
    results.append(("Доступные IP адреса", test_available_ips()))
    
    print("\n" + "="*50)
    print("📊 Результаты тестирования:")
    print("="*50)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n✅ Все тесты прошли успешно!")
    else:
        print("\n❌ Некоторые тесты не прошли. Проверьте настройки подключения.")

