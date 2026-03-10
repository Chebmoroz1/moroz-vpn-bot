"""Веб-сервер для отдачи VPN конфигураций"""
import os
import secrets
from pathlib import Path
from flask import Flask, send_file, abort
from config import VPN_CONFIGS_DIR, BASE_DIR
from database import SessionLocal, VPNKey

app = Flask(__name__)


def get_key_name_by_token(token: str) -> str:
    """Получение имени ключа по токену из БД"""
    db = SessionLocal()
    try:
        vpn_key = db.query(VPNKey).filter(VPNKey.download_token == token).first()
        if vpn_key and vpn_key.is_active:
            return vpn_key.key_name
        return None
    except Exception as e:
        app.logger.error(f"Error getting key by token: {e}")
        return None
    finally:
        db.close()


@app.route('/vpn-config/<token>')
def download_config(token: str):
    """Скачивание VPN конфигурации по токену"""
    key_name = get_key_name_by_token(token)
    
    if not key_name:
        abort(404, description="Конфигурация не найдена")
    
    config_path = VPN_CONFIGS_DIR / f"{key_name}.conf"
    
    if not config_path.exists():
        abort(404, description="Файл конфигурации не найден")
    
    return send_file(
        config_path,
        as_attachment=True,
        download_name=f"{key_name}.conf",
        mimetype='text/plain'
    )


@app.route('/vpn-config/<token>/info')
def config_info(token: str):
    """Информация о конфигурации"""
    key_name = get_key_name_by_token(token)
    
    if not key_name:
        abort(404, description="Конфигурация не найдена")
    
    config_path = VPN_CONFIGS_DIR / f"{key_name}.conf"
    
    if not config_path.exists():
        abort(404, description="Файл конфигурации не найден")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config_content = f.read()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>VPN Конфигурация: {key_name}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
            }}
            .download-btn {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 20px 0;
            }}
            .download-btn:hover {{
                background-color: #0056b3;
            }}
            .config-content {{
                background-color: #f8f9fa;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
                font-family: monospace;
                font-size: 12px;
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 VPN Конфигурация</h1>
            <p><strong>Имя ключа:</strong> {key_name}</p>
            <a href="/vpn-config/{token}" class="download-btn">⬇️ Скачать конфигурацию</a>
            <h2>Содержимое конфигурации:</h2>
            <div class="config-content">{config_content}</div>
        </div>
    </body>
    </html>
    """
    
    return html


def is_port_available(port: int, host: str = '127.0.0.1') -> bool:
    """Проверка доступности порта"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex((host, port))
        sock.close()
        return result != 0  # Порт свободен, если не удалось подключиться
    except:
        sock.close()
        return True


def find_free_port(start_port: int, host: str = '127.0.0.1', max_attempts: int = 10) -> int:
    """Поиск свободного порта"""
    import socket
    for i in range(max_attempts):
        test_port = start_port + i
        if is_port_available(test_port, host):
            return test_port
    raise Exception(f"Не удалось найти свободный порт, начиная с {start_port}")


def run_web_server(host='0.0.0.0', port=5000, debug=False):
    """Запуск веб-сервера"""
    # Проверяем доступность порта
    check_host = '127.0.0.1' if host == '0.0.0.0' else host
    
    if not is_port_available(port, check_host):
        print(f"⚠️ Порт {port} занят, ищем свободный порт...")
        port = find_free_port(port, check_host)
        print(f"✅ Используем порт {port}")
        print(f"📝 Обновите WEB_SERVER_URL в .env на: http://localhost:{port}")
    
    print(f"🚀 Запуск веб-сервера на {host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    run_web_server(debug=True)

