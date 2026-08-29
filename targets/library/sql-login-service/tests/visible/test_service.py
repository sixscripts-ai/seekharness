import sqlite3
import service

def db():
    c = sqlite3.connect(":memory:")
    service.setup(c)
    return c

def test_valid_login():
    assert service.login(db(), "alice", "wonder") == "user"

def test_wrong_password():
    assert service.login(db(), "alice", "nope") is None

def test_admin_search_is_public_only():
    rows = service.search_users(db(), "admin", "a")
    assert rows == [{"username":"admin","role":"admin"}, {"username":"alice","role":"user"}]
