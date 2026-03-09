"""
Database module for MOROZ VPN Bot.

SQLAlchemy 2.0 models and database initialization with SQLite WAL mode.
Provides User, VPNKey, UserMessage, TrafficStatistic, and AppConfig models,
along with engine setup, session management, and retry logic.
"""

import logging
import time
from contextlib import contextmanager

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Date,
    BigInteger,
    ForeignKey,
    func,
    event,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from sqlalchemy.exc import OperationalError, DatabaseError

from config import DATABASE_URL, DATABASE_PATH

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Base
# ──────────────────────────────────────────────
Base = declarative_base()


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────

class User(Base):
    """Telegram user model."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=True)
    username = Column(String(255))
    phone_number = Column(String(20))
    first_name = Column(String(255))
    last_name = Column(String(255))
    nickname = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=False)
    max_keys = Column(Integer, default=0)
    is_admin = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    activation_requested = Column(Boolean, default=False)
    activation_requested_at = Column(DateTime, nullable=True)

    # Relationships
    keys = relationship("VPNKey", back_populates="user")
    messages = relationship("UserMessage", back_populates="user")

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, telegram_id={self.telegram_id}, "
            f"username='{self.username}', is_active={self.is_active})>"
        )


class VPNKey(Base):
    """VPN key / WireGuard peer model."""

    __tablename__ = "vpn_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key_name = Column(String(255), unique=True, nullable=False)
    config_file_path = Column(String(500))
    qr_code_path = Column(String(500))
    protocol = Column(String(50), default="amneziawg")
    client_ip = Column(String(50))
    public_key = Column(String(255))
    private_key = Column(String(255))
    created_by_bot = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    last_used = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="keys")
    traffic_stats = relationship("TrafficStatistic", back_populates="vpn_key")

    def __repr__(self) -> str:
        return (
            f"<VPNKey(id={self.id}, key_name='{self.key_name}', "
            f"user_id={self.user_id}, is_active={self.is_active})>"
        )


class UserMessage(Base):
    """Message / request from user to administrator."""

    __tablename__ = "user_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_type = Column(String(50), nullable=False)          # question, key_request, problem, other
    message_text = Column(String(2000), nullable=False)
    admin_reply = Column(String(2000), nullable=True)
    status = Column(String(50), default="pending")             # pending, replied, resolved, rejected
    created_at = Column(DateTime, default=func.now())
    replied_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="messages")

    def __repr__(self) -> str:
        return (
            f"<UserMessage(id={self.id}, user_id={self.user_id}, "
            f"type='{self.message_type}', status='{self.status}')>"
        )


class TrafficStatistic(Base):
    """Traffic snapshot collected periodically from WireGuard."""

    __tablename__ = "traffic_statistics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vpn_key_id = Column(Integer, ForeignKey("vpn_keys.id"), nullable=False)
    date = Column(Date, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=func.now())
    bytes_received = Column(BigInteger, default=0)
    bytes_sent = Column(BigInteger, default=0)
    connection_ips = Column(String(1000), nullable=True)
    last_connection = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    vpn_key = relationship("VPNKey", back_populates="traffic_stats")

    def __repr__(self) -> str:
        return (
            f"<TrafficStatistic(id={self.id}, vpn_key_id={self.vpn_key_id}, "
            f"date={self.date}, rx={self.bytes_received}, tx={self.bytes_sent})>"
        )


class AppConfig(Base):
    """Application-wide configuration stored in DB (overrides .env)."""

    __tablename__ = "app_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(String(2000), nullable=True)
    description = Column(String(500), nullable=True)
    is_secret = Column(Boolean, default=False)
    category = Column(String(50), default="general")           # telegram, vpn, general, access
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return (
            f"<AppConfig(id={self.id}, key='{self.key}', "
            f"category='{self.category}')>"
        )


# ──────────────────────────────────────────────
# Engine & Session
# ──────────────────────────────────────────────

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,
    echo=False,
    connect_args={"timeout": 30},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Apply SQLite performance and reliability PRAGMAs on every new connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA busy_timeout=30000;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA temp_store=MEMORY;")
    cursor.execute("PRAGMA mmap_size=268435456;")  # 256 MB
    cursor.close()


# Register the PRAGMA handler for every new raw DBAPI connection.
event.listen(engine, "connect", _set_sqlite_pragmas)


# ──────────────────────────────────────────────
# Initialization
# ──────────────────────────────────────────────

def init_db() -> None:
    """
    Create all tables (if they don't exist) and verify SQLite PRAGMAs.

    Should be called once at application startup.
    """
    logger.info("Initializing database at %s …", DATABASE_PATH)

    # Create tables
    Base.metadata.create_all(bind=engine)
    logger.info("All tables created / verified.")

    # Verify PRAGMAs by opening a test connection
    with engine.connect() as conn:
        journal_mode = conn.exec_driver_sql("PRAGMA journal_mode;").scalar()
        foreign_keys = conn.exec_driver_sql("PRAGMA foreign_keys;").scalar()
        logger.info(
            "SQLite PRAGMAs — journal_mode=%s, foreign_keys=%s",
            journal_mode,
            foreign_keys,
        )

    logger.info("Database initialization complete.")


# ──────────────────────────────────────────────
# Session context manager (with retry)
# ──────────────────────────────────────────────

@contextmanager
def get_db_session(max_retries: int = 3, retry_delay: float = 0.5):
    """
    Context manager that yields a SQLAlchemy ``Session``.

    Automatically commits on success, rolls back on error, and retries
    up to *max_retries* times when an ``OperationalError`` or
    ``DatabaseError`` is raised (e.g. database-is-locked scenarios).

    Usage::

        with get_db_session() as session:
            user = session.query(User).filter_by(telegram_id=12345).first()
    """
    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        session: Session = SessionLocal()
        try:
            yield session
            session.commit()
            return  # success — exit the generator
        except (OperationalError, DatabaseError) as exc:
            session.rollback()
            last_exception = exc
            logger.warning(
                "Database error on attempt %d/%d: %s",
                attempt,
                max_retries,
                exc,
            )
            if attempt < max_retries:
                time.sleep(retry_delay * attempt)  # linear back-off
            # On the last attempt the exception will be re-raised below.
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # All retries exhausted — propagate the last database error.
    if last_exception is not None:
        logger.error(
            "Database operation failed after %d retries: %s",
            max_retries,
            last_exception,
        )
        raise last_exception
