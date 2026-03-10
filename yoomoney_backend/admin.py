"""
Админ-панель для бэкенда ЮMoney
"""
import os
from flask import Flask, render_template_string, request, redirect, url_for, jsonify
from datetime import datetime
import sqlite3
from functools import wraps

# Простой HTML шаблон для админки
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Админ-панель ЮMoney</title>
    <meta charset="utf-8">
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            background: #2c3e50;
            color: white;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stat-card h3 {
            margin: 0 0 10px 0;
            color: #7f8c8d;
            font-size: 14px;
        }
        .stat-card .value {
            font-size: 32px;
            font-weight: bold;
            color: #2c3e50;
        }
        table {
            width: 100%;
            background: white;
            border-collapse: collapse;
            border-radius: 5px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background: #34495e;
            color: white;
        }
        tr:hover {
            background: #f5f5f5;
        }
        .status-success {
            color: #27ae60;
            font-weight: bold;
        }
        .status-pending {
            color: #f39c12;
            font-weight: bold;
        }
        .btn {
            display: inline-block;
            padding: 10px 20px;
            background: #3498db;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            margin: 5px;
        }
        .btn:hover {
            background: #2980b9;
        }
        .btn-danger {
            background: #e74c3c;
        }
        .btn-danger:hover {
            background: #c0392b;
        }
        .search-box {
            margin: 20px 0;
            padding: 10px;
            width: 300px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>💰 Админ-панель ЮMoney</h1>
        <p>Управление донатами и настройками</p>
    </div>

    <div class="stats">
        <div class="stat-card">
            <h3>Всего донатов</h3>
            <div class="value">{{ total_donations }}</div>
        </div>
        <div class="stat-card">
            <h3>Успешных</h3>
            <div class="value" style="color: #27ae60;">{{ successful_donations }}</div>
        </div>
        <div class="stat-card">
            <h3>Ожидающих</h3>
            <div class="value" style="color: #f39c12;">{{ pending_donations }}</div>
        </div>
        <div class="stat-card">
            <h3>Общая сумма</h3>
            <div class="value" style="color: #3498db;">{{ total_amount }} ₽</div>
        </div>
    </div>

    <div>
        <input type="text" class="search-box" placeholder="Поиск по Telegram ID..." 
               id="searchInput" onkeyup="filterTable()">
        <a href="/admin" class="btn">Обновить</a>
        <a href="/admin/export" class="btn">Экспорт CSV</a>
    </div>

    <table id="donationsTable">
        <thead>
            <tr>
                <th>ID</th>
                <th>Telegram ID</th>
                <th>Сумма</th>
                <th>Статус</th>
                <th>Operation ID</th>
                <th>Label</th>
                <th>Дата</th>
            </tr>
        </thead>
        <tbody>
            {% for donation in donations %}
            <tr>
                <td>{{ donation.id }}</td>
                <td>{{ donation.telegram_id }}</td>
                <td>{{ donation.amount }} ₽</td>
                <td class="status-{{ donation.status }}">
                    {{ '✅ Успешно' if donation.status == 'success' else '⏳ Ожидает' if donation.status == 'pending' else donation.status }}
                </td>
                <td>{{ donation.operation_id or '-' }}</td>
                <td style="font-size: 11px;">{{ donation.label }}</td>
                <td>{{ donation.timestamp }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <script>
        function filterTable() {
            var input = document.getElementById("searchInput");
            var filter = input.value.toUpperCase();
            var table = document.getElementById("donationsTable");
            var tr = table.getElementsByTagName("tr");

            for (var i = 1; i < tr.length; i++) {
                var td = tr[i].getElementsByTagName("td")[1];
                if (td) {
                    var txtValue = td.textContent || td.innerText;
                    if (txtValue.toUpperCase().indexOf(filter) > -1) {
                        tr[i].style.display = "";
                    } else {
                        tr[i].style.display = "none";
                    }
                }
            }
        }
    </script>
</body>
</html>
"""

def get_db_connection(db_path='db.sqlite'):
    """Получить соединение с БД"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def check_auth(username, password):
    """Проверка авторизации"""
    admin_username = os.getenv('ADMIN_USERNAME', 'admin')
    admin_password = os.getenv('ADMIN_PASSWORD', 'admin')
    return username == admin_username and password == admin_password

def requires_auth(f):
    """Декоратор для защиты роутов"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return ('Необходима авторизация', 401,
                    {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return f(*args, **kwargs)
    return decorated

def init_admin_routes(app, db_path='db.sqlite'):
    """Инициализация админ-роутов"""
    
    @app.route('/admin')
    @requires_auth
    def admin_panel():
        """Главная страница админки"""
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Статистика
        cursor.execute('SELECT COUNT(*) FROM donations')
        total_donations = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM donations WHERE status = 'success'")
        successful_donations = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM donations WHERE status = 'pending'")
        pending_donations = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(amount) FROM donations WHERE status = 'success'")
        total_amount = cursor.fetchone()[0] or 0
        
        # Список донатов
        cursor.execute('''
            SELECT * FROM donations 
            ORDER BY timestamp DESC 
            LIMIT 100
        ''')
        donations = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return render_template_string(ADMIN_TEMPLATE,
            total_donations=total_donations,
            successful_donations=successful_donations,
            pending_donations=pending_donations,
            total_amount=round(total_amount, 2),
            donations=donations
        )
    
    @app.route('/admin/api/stats')
    @requires_auth
    def admin_api_stats():
        """API для получения статистики"""
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM donations')
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM donations WHERE status = 'success'")
        successful = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM donations WHERE status = 'pending'")
        pending = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(amount) FROM donations WHERE status = 'success'")
        total_amount = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return jsonify({
            'total_donations': total,
            'successful_donations': successful,
            'pending_donations': pending,
            'total_amount': round(total_amount, 2)
        })
    
    @app.route('/admin/api/donations')
    @requires_auth
    def admin_api_donations():
        """API для получения списка донатов"""
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        telegram_id = request.args.get('telegram_id', type=int)
        
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        if telegram_id:
            cursor.execute('''
                SELECT * FROM donations 
                WHERE telegram_id = ?
                ORDER BY timestamp DESC 
                LIMIT ? OFFSET ?
            ''', (telegram_id, limit, offset))
        else:
            cursor.execute('''
                SELECT * FROM donations 
                ORDER BY timestamp DESC 
                LIMIT ? OFFSET ?
            ''', (limit, offset))
        
        donations = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify(donations)
    
    @app.route('/admin/export')
    @requires_auth
    def admin_export():
        """Экспорт донатов в CSV"""
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM donations ORDER BY timestamp DESC')
        donations = cursor.fetchall()
        conn.close()
        
        csv_data = "ID,Telegram ID,Сумма,Статус,Operation ID,Label,Дата\n"
        for row in donations:
            csv_data += f"{row['id']},{row['telegram_id']},{row['amount']},{row['status']},{row['operation_id'] or ''},{row['label']},{row['timestamp']}\n"
        
        from flask import Response
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=donations.csv'}
        )
    
    @app.route('/admin/config')
    @requires_auth
    def admin_config():
        """Просмотр конфигурации"""
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM config')
        config_items = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        # Скрываем чувствительные данные
        for item in config_items:
            if 'token' in item['key'].lower() or 'secret' in item['key'].lower():
                item['value'] = item['value'][:10] + '...' if len(item['value']) > 10 else '***'
        
        return jsonify(config_items)

