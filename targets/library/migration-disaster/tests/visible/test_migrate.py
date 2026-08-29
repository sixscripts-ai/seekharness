import sqlite3
from migrations import migrate

def legacy():
    c=sqlite3.connect(":memory:")
    c.execute("create table users(id integer primary key, email text unique)")
    c.execute("insert into users(email) values ('alice@example.com')")
    c.execute("pragma user_version=1")
    return c

def test_preserves_row_and_adds_columns():
    c=legacy(); migrate(c)
    row=c.execute("select email,display_name,active from users").fetchone()
    assert row == ("alice@example.com","alice",1)
    assert c.execute("pragma user_version").fetchone()[0] == 3
