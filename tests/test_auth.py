import os
import tempfile

import pytest

from backend import auth


def test_password_hashing():
    pw = "SecretPassword123!"
    h, salt = auth.hash_password(pw)
    assert h != pw
    assert len(salt) > 0
    assert auth.verify_password(pw, h, salt) is True
    assert auth.verify_password("WrongPassword", h, salt) is False


def test_jwt_token_creation_and_validation():
    secret = "my-super-secret-key-for-testing"
    token = auth.create_access_token("alice", "admin", secret, expires_in_seconds=3600)
    assert token is not None
    payload = auth.decode_access_token(token, secret)
    assert payload is not None
    assert payload["sub"] == "alice"
    assert payload["role"] == "admin"

    # Test tampering
    tampered = token[:-4] + "abcd"
    assert auth.decode_access_token(tampered, secret) is None

    # Test expired token
    expired_token = auth.create_access_token("bob", "user", secret, expires_in_seconds=-10)
    assert auth.decode_access_token(expired_token, secret) is None


def test_user_db_lifecycle(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = os.path.join(tmpdir, "test_users.db")
        monkeypatch.setenv("USERS_DB_PATH", test_db)

        auth.init_db()
        assert auth.count_users() == 0

        # Create admin
        admin = auth.create_user("admin", "AdminPass123", role="admin")
        assert admin.username == "admin"
        assert admin.role == "admin"
        assert auth.count_users() == 1

        # Duplicate username should raise ValueError
        with pytest.raises(ValueError, match="вже існує"):
            auth.create_user("admin", "AnotherPass")

        # Create regular user
        user = auth.create_user("john", "JohnPass123", role="user")
        assert user.username == "john"
        assert user.role == "user"
        assert auth.count_users() == 2

        # List users
        users = auth.list_users()
        assert len(users) == 2
        usernames = [u.username for u in users]
        assert "admin" in usernames and "john" in usernames

        # Update password
        auth.update_user_password("john", "NewJohnPass456")
        john_dict = auth.get_user_by_username("john")
        assert auth.verify_password("NewJohnPass456", john_dict["password_hash"], john_dict["salt"]) is True
        assert auth.verify_password("JohnPass123", john_dict["password_hash"], john_dict["salt"]) is False

        # Delete user
        assert auth.delete_user("john") is True
        assert auth.count_users() == 1
        assert auth.get_user_by_username("john") is None
