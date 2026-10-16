import os
import tempfile

from fastapi.testclient import TestClient


def test_api_auth_and_rbac(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = os.path.join(tmpdir, "test_users.db")
        test_settings = os.path.join(tmpdir, "test_settings.json")
        monkeypatch.setenv("USERS_DB_PATH", test_db)
        monkeypatch.setenv("CONFIG_FILE_PATH", test_settings)
        monkeypatch.setenv("JWT_SECRET", "test-secret-key-12345")

        from backend import auth, main

        auth.init_db()

        client = TestClient(main.app)

        # 1. Setup status should be true
        res = client.get("/api/auth/setup-status")
        assert res.status_code == 200
        assert res.json()["setup_required"] is True

        # 2. Try to access settings without token -> 401
        res = client.get("/api/settings")
        assert res.status_code == 401

        # 3. Perform setup -> create first admin
        res = client.post(
            "/api/auth/setup",
            json={"username": "superadmin", "password": "SuperPassword123"},
        )
        assert res.status_code == 200
        admin_data = res.json()
        assert "token" in admin_data
        admin_token = admin_data["token"]
        assert admin_data["user"]["role"] == "admin"

        # 4. Setup status should now be false
        res = client.get("/api/auth/setup-status")
        assert res.status_code == 200
        assert res.json()["setup_required"] is False

        # 5. Calling setup again should be 403 Forbidden
        res = client.post("/api/auth/setup", json={"username": "hacker", "password": "HackerPassword"})
        assert res.status_code == 403

        # 6. Admin can access settings
        headers_admin = {"Authorization": f"Bearer {admin_token}"}
        res = client.get("/api/settings", headers=headers_admin)
        assert res.status_code == 200
        assert "torrserver_url" in res.json()
        assert "jwt_secret" not in res.json()  # jwt_secret must not leak

        # 7. Admin creates regular user
        res = client.post(
            "/api/users",
            headers=headers_admin,
            json={
                "username": "viewer",
                "password": "ViewerPassword123",
                "role": "user",
            },
        )
        assert res.status_code == 200
        assert res.json()["user"]["role"] == "user"

        # 8. Regular user logs in
        res = client.post(
            "/api/auth/login",
            json={"username": "viewer", "password": "ViewerPassword123"},
        )
        assert res.status_code == 200
        viewer_token = res.json()["token"]
        headers_viewer = {"Authorization": f"Bearer {viewer_token}"}

        # 9. Regular user checks /api/auth/me
        res = client.get("/api/auth/me", headers=headers_viewer)
        assert res.status_code == 200
        assert res.json()["username"] == "viewer"
        assert res.json()["role"] == "user"

        # 10. Regular user tries to access /api/settings -> 403 FORBIDDEN!
        res = client.get("/api/settings", headers=headers_viewer)
        assert res.status_code == 403
        assert "admin" in res.json()["detail"].lower()

        # 11. Regular user tries to manage users -> 403 FORBIDDEN!
        res = client.get("/api/users", headers=headers_viewer)
        assert res.status_code == 403

        # 12. Regular user changes own password
        res = client.post(
            "/api/auth/change-password",
            headers=headers_viewer,
            json={
                "current_password": "ViewerPassword123",
                "new_password": "NewViewerPassword456",
            },
        )
        assert res.status_code == 200

        # Login with old password fails
        res = client.post(
            "/api/auth/login",
            json={"username": "viewer", "password": "ViewerPassword123"},
        )
        assert res.status_code == 401

        # Login with new password succeeds
        res = client.post(
            "/api/auth/login",
            json={"username": "viewer", "password": "NewViewerPassword456"},
        )
        assert res.status_code == 200
