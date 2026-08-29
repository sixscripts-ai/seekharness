import sqlite3

def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("pragma user_version").fetchone()[0]
    if version < 2:
        conn.execute("alter table users add column display_name text")
        conn.execute("update users set display_name = substr(email, 1, instr(email, '@') - 1) where display_name is null")
        conn.execute("pragma user_version=2")
        version = 2
    if version < 3:
        conn.execute("alter table users add column active integer not null default 1")
        conn.execute("pragma user_version=3")
    conn.commit()
