"""Единая конфигурация подключения к PostgreSQL.

Приоритет:
  1. DATABASE_URL (стандартная строка вида postgresql://user:pass@host:5432/db)
  2. Переменные DB_NAME / DB_HOST / DB_PORT / DB_USER / DB_PASSWORD
  3. Локальный unix-сокет и текущий пользователь ОС (macOS/Linux, peer/trust)
"""
import os

import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")

DB_CONFIG = {"dbname": os.getenv("DB_NAME", "stock_prediction")}

for _key, _env in (
    ("host", "DB_HOST"),
    ("port", "DB_PORT"),
    ("user", "DB_USER"),
    ("password", "DB_PASSWORD"),
):
    _value = os.getenv(_env)
    if _value:
        DB_CONFIG[_key] = _value


def connect():
    """Новое соединение с БД. Вызывающий код отвечает за закрытие."""
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(**DB_CONFIG)
