import sqlite3
from migrations import migrate

def legacy(rows):
    c=sqlite3.connect(":memory:")
    c.execute("create table users(id integer primary key, email text unique)")
    c.executemany("insert into users(email) values (?)", [(r,) for r in rows])
    c.execute("pragma user_version=1")
    return c

def test_multiple_rows_preserved():
    c=legacy(["a@x.com","bob@example.com"]); migrate(c)
    assert c.execute("select count(*) from users").fetchone()[0] == 2

def test_idempotent():
    c=legacy(["a@x.com"]); migrate(c); migrate(c)
    assert c.execute("select count(*) from users").fetchone()[0] == 1
    assert [r[1] for r in c.execute("pragma table_info(users)")] == ["id","email","display_name","active"]

def test_existing_ids_preserved():
    c=legacy(["a@x.com"]); before=c.execute("select id from users").fetchone()[0]; migrate(c)
    assert c.execute("select id from users").fetchone()[0] == before
