"""Запуск веб-сервера для отдачи VPN конфигураций"""
from web_server import run_web_server
from config import WEB_SERVER_HOST, WEB_SERVER_PORT

if __name__ == "__main__":
    print(f"🚀 Запуск веб-сервера на {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    print(f"📡 URL: http://{WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    run_web_server(host=WEB_SERVER_HOST, port=WEB_SERVER_PORT, debug=False)

