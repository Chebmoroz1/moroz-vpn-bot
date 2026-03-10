"""Модели базы данных и работа с БД"""
from datetime import datetime, date
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Float, BigInteger, Date, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import StaticPool, QueuePool
from config import DATABASE_PATH
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import sqlalchemy.exc
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()


class User(Base):
    """Модель пользователя"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=True)  # Может быть None для пользователей, добавленных только по номеру
    username = Column(String(255))
    phone_number = Column(String(20))
    first_name = Column(String(255))
    last_name = Column(String(255))
    nickname = Column(String(255), nullable=True)  # Никнейм пользователя (для отображения в боте)
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    max_keys = Column(Integer, default=1)
    is_admin = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)  # Soft delete для восстановления
    deleted_at = Column(DateTime, nullable=True)  # Дата удаления
    activation_requested = Column(Boolean, default=False)  # Запрошена ли активация
    activation_requested_at = Column(DateTime, nullable=True)  # Дата запроса активации

    # Связь с ключами
    vpn_keys = relationship("VPNKey", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username}, nickname={self.nickname}, is_active={self.is_active})>"


class VPNKey(Base):
    """Модель VPN ключа"""
    __tablename__ = 'vpn_keys'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    key_name = Column(String(255), unique=True, nullable=False)
    config_file_path = Column(String(500))
    qr_code_path = Column(String(500))
    protocol = Column(String(50), default='amneziawg')
    created_at = Column(DateTime, default=datetime.now)
    last_used = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    client_ip = Column(String(50))  # IP адрес клиента (10.8.1.X)
    public_key = Column(String(255))  # Публичный ключ клиента
    private_key = Column(String(255))  # Приватный ключ клиента (зашифрован или захеширован)
    download_token = Column(String(255))  # Токен для доступа к конфигурации через веб
    created_by_bot = Column(Boolean, default=True)  # Создан ли ключ через бота (True) или вручную/AmneziaVPN (False)
    
    # Новые поля для биллинга
    access_type = Column(String(50), default='paid')  # 'test' | 'paid' | 'free' | 'donation'
    subscription_period_days = Column(Integer, nullable=True)  # Период подписки в днях
    purchase_date = Column(DateTime, nullable=True)  # Дата покупки
    payment_id = Column(Integer, ForeignKey('payments.id'), nullable=True)  # Связь с платежом
    is_test = Column(Boolean, default=False)  # Тестовый доступ
    reminder_sent = Column(Boolean, default=False)  # Отправлено ли напоминание

    # Связь с пользователем
    user = relationship("User", back_populates="vpn_keys")
    # Связь с платежом
    payment = relationship("Payment", backref="vpn_keys")

    def __repr__(self):
        return f"<VPNKey(key_name={self.key_name}, protocol={self.protocol}, is_active={self.is_active}, access_type={self.access_type})>"


class Payment(Base):
    """Модель платежа"""
    __tablename__ = 'payments'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    amount = Column(String(20), nullable=False)  # Сумма платежа
    currency = Column(String(10), default='RUB')  # Валюта
    status = Column(String(50), default='pending')  # pending, success, failed, cancelled
    payment_method = Column(String(50), default='yoomoney')  # Метод оплаты
    payment_type = Column(String(50), default='donation')  # 'donation' | 'qr_subscription' | 'test'
    yoomoney_payment_id = Column(String(255), nullable=True)  # ID платежа в YooMoney
    yoomoney_label = Column(String(255), unique=True, nullable=False)  # Уникальный label для YooMoney
    payment_url = Column(String(500), nullable=True)  # URL для оплаты
    created_at = Column(DateTime, default=datetime.now)
    paid_at = Column(DateTime, nullable=True)  # Дата оплаты
    expires_at = Column(DateTime, nullable=True)  # Дата истечения платежной ссылки
    
    # Дополнительные данные
    description = Column(String(500), nullable=True)  # Описание платежа
    metadata_json = Column(String(1000), nullable=True)  # JSON метаданные (переименовано из metadata, так как metadata зарезервировано в SQLAlchemy)
    
    # Поля для подписок на QR-коды
    qr_code_count = Column(Integer, nullable=True)  # Количество QR-кодов
    subscription_period_days = Column(Integer, nullable=True)  # Период подписки в днях
    is_test = Column(Boolean, default=False)  # Тестовый доступ

    # Связь с пользователем
    user = relationship("User", backref="payments")

    def __repr__(self):
        return f"<Payment(id={self.id}, amount={self.amount}, status={self.status}, payment_type={self.payment_type}, yoomoney_label={self.yoomoney_label})>"


class AppConfig(Base):
    """Модель настроек приложения (для хранения секретов и динамических настроек)"""
    __tablename__ = 'app_config'

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)  # Ключ настройки
    value = Column(String(2000), nullable=True)  # Значение настройки
    description = Column(String(500), nullable=True)  # Описание настройки
    is_secret = Column(Boolean, default=False)  # Является ли настройка секретной (скрывать в интерфейсе)
    category = Column(String(50), default='general')  # Категория настройки (telegram, yoomoney, vpn, general)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<AppConfig(key={self.key}, category={self.category})>"


class TrafficStatistics(Base):
    """Статистика трафика по ключам (snapshots каждые 15 минут)"""
    __tablename__ = 'traffic_statistics'

    id = Column(Integer, primary_key=True)
    vpn_key_id = Column(Integer, ForeignKey('vpn_keys.id'), nullable=False)
    date = Column(Date, nullable=False)  # Дата статистики
    timestamp = Column(DateTime, nullable=False, default=datetime.now)  # Время snapshot (для вычисления трафика за интервал)
    bytes_received = Column(BigInteger, default=0)  # Входящий трафик (накопительный)
    bytes_sent = Column(BigInteger, default=0)  # Исходящий трафик (накопительный)
    connection_ips = Column(String(1000), nullable=True)  # JSON массив IP адресов (последние 5-10)
    last_connection = Column(DateTime, nullable=True)  # Последнее подключение
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связь с ключом
    vpn_key = relationship("VPNKey", backref="traffic_stats")
    
    # Индекс для быстрого поиска по ключу и времени
    __table_args__ = (
        {'sqlite_autoincrement': True}
    )

    def __repr__(self):
        return f"<TrafficStatistics(vpn_key_id={self.vpn_key_id}, date={self.date}, bytes_received={self.bytes_received}, bytes_sent={self.bytes_sent})>"


# Инициализация базы данных с оптимизациями для конкурентного доступа
# Используем QueuePool для лучшей производительности при конкурентных запросах
# WAL mode будет включен в init_db()
engine = create_engine(
    f'sqlite:///{DATABASE_PATH}',
    echo=False,
    poolclass=QueuePool,
    pool_size=10,  # Количество соединений в пуле
    max_overflow=20,  # Максимальное количество дополнительных соединений
    pool_pre_ping=True,  # Проверка соединений перед использованием
    connect_args={
        'check_same_thread': False,  # Разрешаем использование из разных потоков
        'timeout': 30.0,  # Timeout для операций с БД (30 секунд)
    }
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db():
    """Инициализация базы данных (создание таблиц)"""
    Base.metadata.create_all(engine)
    
    # Включаем WAL mode для лучшей конкурентности
    # WAL (Write-Ahead Logging) позволяет читать и писать одновременно
    try:
        with engine.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")  # Баланс между производительностью и надежностью
            conn.execute("PRAGMA busy_timeout=30000")  # 30 секунд timeout для блокировок
            conn.execute("PRAGMA foreign_keys=ON")  # Включаем внешние ключи
            conn.execute("PRAGMA temp_store=MEMORY")  # Временные таблицы в памяти
            conn.execute("PRAGMA mmap_size=268435456")  # 256MB для mmap (ускоряет чтение)
            conn.commit()
        logger.info("SQLite оптимизирован: WAL mode включен, настройки применены")
    except Exception as e:
        import logging
        logging.warning(f"Не удалось применить оптимизации SQLite: {e}")
    
    # Выполняем миграции для существующих таблиц
    try:
        import sqlite3
        from pathlib import Path
        
        db_path = Path(DATABASE_PATH)
        if not db_path.exists():
            return
        
        # Используем прямой доступ к SQLite для миграции
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        cursor = conn.cursor()
        
        # Включаем WAL mode и оптимизации для миграций
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        
        # Получаем список всех колонок для каждой таблицы
        def get_columns(table_name):
            cursor.execute(f"PRAGMA table_info({table_name})")
            return [row[1] for row in cursor.fetchall()]
        
        # Миграция для таблицы users
        user_columns = get_columns('users')
        if 'nickname' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN nickname VARCHAR(255)")
            conn.commit()
        if 'is_deleted' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_deleted BOOLEAN DEFAULT 0")
            conn.commit()
        if 'deleted_at' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP")
            conn.commit()
        if 'activation_requested' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN activation_requested BOOLEAN DEFAULT 0")
            conn.commit()
        if 'activation_requested_at' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN activation_requested_at TIMESTAMP")
            conn.commit()
        # Разрешаем telegram_id быть NULL для пользователей, добавленных только по номеру
        # SQLite не поддерживает изменение NOT NULL, поэтому это делается при создании таблицы
        # Для существующих записей это не критично
        
        # Миграция для таблицы vpn_keys
        vpn_key_columns = get_columns('vpn_keys')
        if 'created_by_bot' not in vpn_key_columns:
            cursor.execute("ALTER TABLE vpn_keys ADD COLUMN created_by_bot BOOLEAN DEFAULT 1")
            cursor.execute("UPDATE vpn_keys SET created_by_bot = 1")
            conn.commit()
        if 'access_type' not in vpn_key_columns:
            cursor.execute("ALTER TABLE vpn_keys ADD COLUMN access_type VARCHAR(50) DEFAULT 'paid'")
            conn.commit()
        if 'subscription_period_days' not in vpn_key_columns:
            cursor.execute("ALTER TABLE vpn_keys ADD COLUMN subscription_period_days INTEGER")
            conn.commit()
        if 'purchase_date' not in vpn_key_columns:
            cursor.execute("ALTER TABLE vpn_keys ADD COLUMN purchase_date TIMESTAMP")
            conn.commit()
        if 'payment_id' not in vpn_key_columns:
            cursor.execute("ALTER TABLE vpn_keys ADD COLUMN payment_id INTEGER")
            conn.commit()
        if 'is_test' not in vpn_key_columns:
            cursor.execute("ALTER TABLE vpn_keys ADD COLUMN is_test BOOLEAN DEFAULT 0")
            conn.commit()
        if 'reminder_sent' not in vpn_key_columns:
            cursor.execute("ALTER TABLE vpn_keys ADD COLUMN reminder_sent BOOLEAN DEFAULT 0")
            conn.commit()
        
        # Миграция для таблицы traffic_statistics
        traffic_stats_columns = get_columns('traffic_statistics')
        if 'timestamp' not in traffic_stats_columns:
            cursor.execute("ALTER TABLE traffic_statistics ADD COLUMN timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            # Устанавливаем timestamp = created_at для существующих записей
            cursor.execute("UPDATE traffic_statistics SET timestamp = created_at WHERE timestamp IS NULL")
            conn.commit()
            logger.info("Added timestamp column to traffic_statistics table")
        
        # Миграция для таблицы payments
        payment_columns = get_columns('payments')
        if 'payment_type' not in payment_columns:
            cursor.execute("ALTER TABLE payments ADD COLUMN payment_type VARCHAR(50) DEFAULT 'donation'")
            conn.commit()
        if 'qr_code_count' not in payment_columns:
            cursor.execute("ALTER TABLE payments ADD COLUMN qr_code_count INTEGER")
            conn.commit()
        if 'subscription_period_days' not in payment_columns:
            cursor.execute("ALTER TABLE payments ADD COLUMN subscription_period_days INTEGER")
            conn.commit()
        if 'is_test' not in payment_columns:
            cursor.execute("ALTER TABLE payments ADD COLUMN is_test BOOLEAN DEFAULT 0")
            conn.commit()
        
        # Проверяем, существует ли таблица app_config
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_config'")
        if not cursor.fetchone():
            # Создаем таблицу app_config
            cursor.execute("""
                CREATE TABLE app_config (
                    id INTEGER PRIMARY KEY,
                    key VARCHAR(100) NOT NULL UNIQUE,
                    value VARCHAR(2000),
                    description VARCHAR(500),
                    is_secret BOOLEAN DEFAULT 0,
                    category VARCHAR(50) DEFAULT 'general',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        
        # Проверяем, существует ли таблица traffic_statistics
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='traffic_statistics'")
        if not cursor.fetchone():
            # Создаем таблицу traffic_statistics
            cursor.execute("""
                CREATE TABLE traffic_statistics (
                    id INTEGER PRIMARY KEY,
                    vpn_key_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    bytes_received INTEGER DEFAULT 0,
                    bytes_sent INTEGER DEFAULT 0,
                    connection_ips VARCHAR(1000),
                    last_connection TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (vpn_key_id) REFERENCES vpn_keys(id)
                )
            """)
            conn.commit()
        
        cursor.close()
        conn.close()
    except Exception as e:
        # Если миграция не удалась, продолжаем работу
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to migrate database: {e}")


def get_db():
    """Получение сессии БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=0.1, max=2),
    retry=retry_if_exception_type((sqlalchemy.exc.OperationalError, sqlalchemy.exc.DatabaseError)),
    reraise=True
)
def get_db_session():
    """
    Получение сессии БД (для прямого использования)
    С автоматическим retry при блокировке БД
    """
    return SessionLocal()


def db_retry(max_attempts=3):
    """
    Декоратор для retry операций с БД
    Использование:
        @db_retry(max_attempts=3)
        def my_db_operation():
            db = get_db_session()
            try:
                # операции с БД
                db.commit()
            finally:
                db.close()
    """
    def decorator(func):
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=0.1, max=2),
            retry=retry_if_exception_type((sqlalchemy.exc.OperationalError, sqlalchemy.exc.DatabaseError)),
            reraise=True
        )
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
