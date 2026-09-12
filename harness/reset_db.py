"""Generic SQLite reset helper.

Drops and recreates a database deterministically from a schema file and an
optional seed file. This module is harness-only: it does not know anything
about the application's schema or data.
"""

import os
import sqlite3


def reset_db(db_path, schema_path, seed_path=None, schema_sep=";"):
    """Recreate a clean database from schema.sql (and optionally seed.sql).

    The database file is deleted first so every run starts identical.
    """
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        if seed_path and os.path.exists(seed_path):
            with open(seed_path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
        conn.commit()
    finally:
        conn.close()
    return db_path


def ensure_reset(root_dir, db_name="app.db"):
    """Point the app at a disposible DB under root_dir and reset it."""
    import os

    db_path = os.path.join(root_dir, db_name)
    schema_path = os.path.join(root_dir, "schema.sql")
    seed_path = os.path.join(root_dir, "seed.sql")
    reset_db(db_path, schema_path, seed_path)
    return db_path


if __name__ == "__main__":
    import sys

    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = ensure_reset(root)
    print("DB RESET:", path)