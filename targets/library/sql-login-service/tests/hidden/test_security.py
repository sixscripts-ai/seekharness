import sqlite3, pytest
import service

def db():
    c = sqlite3.connect(":memory:")
    service.setup(c)
    return c

def test_login_injection_fails():
    assert service.login(db(), "admin' --", "x") is None
    assert service.login(db(), "' OR 1=1 --", "x") is None

def test_search_requires_admin():
    with pytest.raises(PermissionError):
        service.search_users(db(), "user", "")

def test_search_prefix_is_parameterized():
    rows = service.search_users(db(), "admin", "%' OR 1=1 --")
    assert rows == []

def test_no_password_key():
    assert all("password" not in x for x in service.search_users(db(), "admin", ""))
