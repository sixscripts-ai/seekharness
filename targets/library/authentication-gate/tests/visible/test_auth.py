from fastapi.testclient import TestClient
import app

client = TestClient(app.app)

def test_valid_admin_login_and_access():
    r = client.post("/login", json={"username":"admin","password":"swordfish"})
    assert r.status_code == 200
    token = r.json()["token"]
    r = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

def test_wrong_password_rejected():
    r = client.post("/login", json={"username":"admin","password":"wrong"})
    assert r.status_code in (401, 403)
