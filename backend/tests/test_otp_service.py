from app.core.config import settings
from app.services import otp_service


async def test_generate_and_verify_otp_success() -> None:
    code = await otp_service.generate_otp("login", "user-1")
    assert len(code) == settings.OTP_LENGTH
    assert code.isdigit()

    assert await otp_service.verify_otp("login", "user-1", code) is True


async def test_verify_consumes_the_otp_single_use() -> None:
    code = await otp_service.generate_otp("login", "user-1")
    assert await otp_service.verify_otp("login", "user-1", code) is True
    assert await otp_service.verify_otp("login", "user-1", code) is False


async def test_verify_wrong_code_fails() -> None:
    await otp_service.generate_otp("login", "user-1")
    assert await otp_service.verify_otp("login", "user-1", "000000") is False


async def test_verify_unknown_subject_fails() -> None:
    assert await otp_service.verify_otp("login", "nonexistent-user", "123456") is False


async def test_purposes_are_isolated() -> None:
    login_code = await otp_service.generate_otp("login", "user-1")
    await otp_service.generate_otp("phone_verification", "user-1")

    assert await otp_service.verify_otp("phone_verification", "user-1", login_code) is False
    assert await otp_service.verify_otp("login", "user-1", login_code) is True


async def test_exceeding_max_attempts_invalidates_the_otp() -> None:
    code = await otp_service.generate_otp("login", "user-1")

    for _ in range(settings.OTP_MAX_ATTEMPTS):
        assert await otp_service.verify_otp("login", "user-1", "wrong-code") is False

    # Even the correct code no longer works — the OTP was invalidated after too many tries.
    assert await otp_service.verify_otp("login", "user-1", code) is False


async def test_login_challenge_roundtrip() -> None:
    token = await otp_service.create_login_challenge("user-42")

    challenge = await otp_service.resolve_login_challenge(token)
    assert challenge == {"user_id": "user-42", "remember_device": False, "device_was_known": False}

    await otp_service.consume_login_challenge(token)
    assert await otp_service.resolve_login_challenge(token) is None


async def test_login_challenge_carries_device_decisions() -> None:
    """Step 1's device findings must survive to step 2 — a client cannot be
    trusted to re-assert that its device is already known."""
    token = await otp_service.create_login_challenge("user-42", remember_device=True, device_was_known=True)

    challenge = await otp_service.resolve_login_challenge(token)
    assert challenge["remember_device"] is True
    assert challenge["device_was_known"] is True


async def test_resolve_unknown_challenge_returns_none() -> None:
    assert await otp_service.resolve_login_challenge("not-a-real-token") is None
