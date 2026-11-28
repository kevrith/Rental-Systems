"""What a landlord or caretaker is handed when they issue a code or link.

RentFlow does not text these itself while `OTP_DELIVERY=manual`. The staff member
sees the code once and passes it on through WhatsApp (`wa.me`) or the phone's own
messaging app (`sms:`), so the response carries the recipient's number and a
ready-to-send message alongside the secret.
"""

from pydantic import BaseModel


class HandoverCode(BaseModel):
    code: str
    message: str
    phone_number: str
    recipient_name: str
    expires_in_seconds: int


class HandoverLink(BaseModel):
    link: str
    message: str
    phone_number: str
    recipient_name: str
    # None for links that outlive a single sitting (a signing link lasts days).
    expires_in_seconds: int | None = None


class AuthConfig(BaseModel):
    otp_delivery: str
