from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_volunteer_invite_email(
    to_email: str,
    volunteer_name: str,
    ngo_name: str,
    invite_link: str,
) -> bool:
    if not to_email:
        return False

    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    from_email = os.environ.get("SMTP_FROM") or username or "noreply@foodbridge.dev"

    if not host or not username or not password:
        print(f"[EMAIL] SMTP not configured; invite for {to_email}: {invite_link}")
        return False

    message = EmailMessage()
    message["Subject"] = f"FoodBridge Volunteer Invite - {ngo_name}"
    message["From"] = from_email
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                f"Hi {volunteer_name},",
                "",
                f"You have been invited by {ngo_name} to join FoodBridge as a volunteer.",
                "Complete your registration from this link:",
                invite_link,
                "",
                "After registration, the NGO coordinator will approve your account.",
            ]
        )
    )

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
        return True
    except Exception as exc:
        print(f"[EMAIL] Failed to send invite to {to_email}: {exc}")
        return False
