import sqlite3

def setup(conn: sqlite3.Connection):
    conn.executescript("""
    create table users(username text primary key, password text not null, role text not null);
    insert into users values ('admin','swordfish','admin');
    insert into users values ('alice','wonder','user');
    """)

def login(conn, username: str, password: str):
    row = conn.execute("select role from users where username=? and password=?", (username, password)).fetchone()
    return row[0] if row else None

def search_users(conn, caller_role: str, prefix: str):
    if caller_role != "admin":
        raise PermissionError("admin required")
    rows = conn.execute("select username,role from users where username like ? order by username", (prefix + "%",)).fetchall()
    return [{"username":u,"role":r} for u,r in rows]
