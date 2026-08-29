import sqlite3

def setup(conn: sqlite3.Connection):
    conn.executescript("""
    create table users(username text primary key, password text not null, role text not null);
    insert into users values ('admin','swordfish','admin');
    insert into users values ('alice','wonder','user');
    """)

def login(conn, username: str, password: str):
    # TODO: this is intentionally unsafe.
    q = f"select role from users where username='{username}' and password='{password}'"
    row = conn.execute(q).fetchone()
    return row[0] if row else None

def search_users(conn, caller_role: str, prefix: str):
    # TODO: enforce admin and avoid unsafe SQL / secret leakage.
    rows = conn.execute(f"select username,password,role from users where username like '{prefix}%'").fetchall()
    return [{"username":u,"password":p,"role":r} for u,p,r in rows]
