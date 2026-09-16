"""User lookup. Scenario: MAJOR — a real security bug (SQL injection via
unsanitized string formatting) that needs human attention before merging.
Opening a PR that adds/touches this file should classify as "major" and
route to the Kaggle heavy-tier deep review."""

import sqlite3


def get_user(conn: sqlite3.Connection, username: str):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    return conn.execute(query).fetchone()
