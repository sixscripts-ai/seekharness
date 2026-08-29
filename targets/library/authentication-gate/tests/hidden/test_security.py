from fastapi.testclient import TestClient
import importlib, app

client = TestClient(app.app)

def test_forged_admin_token_rejected():
    r = client.get("/admin", headers={"Authorization":"Bearer admin"})
    assert r.status_code in (401,403)

def test_guest_token_cannot_access_admin():
    r = client.post("/login", json={"username":"guest","password":"guest"})
    assert r.status_code == 200
    token = r.json()["token"]
    r = client.get("/admin", headers={"Authorization":f"Bearer {token}"})
    assert r.status_code == 403

def test_empty_password_rejected():
    r = client.post("/login", json={"username":"admin","password":""})
    assert r.status_code in (401,403)
