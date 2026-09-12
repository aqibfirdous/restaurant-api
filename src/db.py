import os
import sqlite3

DEFAULT_DB_PATH = os.environ.get("RESTAURANT_DB", os.path.join(os.path.dirname(__file__), "..", "restaurant.db"))


def get_db_path():
    return os.path.abspath(os.path.normpath(os.environ.get("RESTAURANT_DB", DEFAULT_DB_PATH)))


def connect(db_path=None):
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def fetch_one(con, query, params=()):
    return con.execute(query, params).fetchone()


def fetch_all(con, query, params=()):
    return con.execute(query, params).fetchall()


def row_to_dict(row):
    return dict(row) if row is not None else None