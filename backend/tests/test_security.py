from app.core.security import create_access_token, decode_token, hash_password, verify_password


def test_hash_password_roundtrip() -> None:
    hashed = hash_password("supersecret123")
    assert hashed != "supersecret123"
    assert verify_password("supersecret123", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_access_token_roundtrip() -> None:
    token = create_access_token(user_id="user-1", org_id="org-1", role="owner")
    payload = decode_token(token)

    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["org_id"] == "org-1"
    assert payload["role"] == "owner"
    assert payload["type"] == "access"


def test_decode_token_rejects_garbage() -> None:
    assert decode_token("not-a-real-token") is None
