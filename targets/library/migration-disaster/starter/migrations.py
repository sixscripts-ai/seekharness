import sqlite3

def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("pragma user_version").fetchone()[0]
    if version < 2:
        # BUG: destructive migration loses existing rows.
        conn.execute("drop table users")
        conn.execute("create table users(id integer primary key, email text unique, display_name text)")
        conn.execute("pragma user_version=2")
    if version < 3:
        # BUG: uses stale version and may run incorrectly.
        conn.execute("alter table users add column active integer not null default 1")
        conn.execute("pragma user_version=3")
    conn.commit()
