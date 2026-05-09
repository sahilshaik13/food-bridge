"""Local smoke test for the PRD spine without calling external cloud APIs."""

from __future__ import annotations

from pathlib import Path
import os
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
os.environ["FIRESTORE_SYNC_ENABLED"] = "false"
sys.path.insert(0, str(BACKEND_DIR))

from app.models import (  # noqa: E402
    CommunicationMessageCreate,
    DonorCreate,
    DonorTelegramUpdate,
    DonationCreate,
    DonationStatus,
    DonationStatusUpdate,
    EmergencyRequestCreate,
    Role,
    TelegramLinkRequest,
)
from app.services.demo_store import DemoStore  # noqa: E402


def main() -> int:
    store = DemoStore()

    donation = store.create_donation(
        DonationCreate(
            donor_id="donor_hitech_banquet",
            food_type="rice and dal",
            quantity_kg=36,
            meal_count=180,
            notes="Packed in sealed containers after lunch service",
        )
    )
    assert donation.scan.passed
    assert donation.ngo_queue
    assert donation.status == DonationStatus.notified

    accepted = store.update_donation_status(
        donation.id,
        DonationStatusUpdate(status=DonationStatus.accepted, ngo_id=donation.ngo_queue[0].ngo_id),
    )
    assert accepted.assigned_ngo_name

    completed = store.update_donation_status(
        donation.id,
        DonationStatusUpdate(
            status=DonationStatus.completed,
            ngo_id=donation.ngo_queue[0].ngo_id,
            volunteer_name="Demo Volunteer",
            meals_served=176,
            pickup_photo_url="/demo/pickup.jpg",
        ),
    )
    assert completed.completed_meals_served == 176

    request = store.create_emergency_request(
        EmergencyRequestCreate(
            ngo_id="ngo_city_meals",
            food_type="roti and dal",
            quantity_goal_kg=60,
            deadline_minutes=90,
        )
    )
    assert request.donor_targets
    assert request.pledged_kg > 0

    registered = store.create_donor(
        DonorCreate(
            name="Smoke Test Kitchen",
            area="Madhapur",
            type="Restaurant",
            fssai_license="13622011007777",
            contact_name="Smoke Manager",
            phone="+91 90000 07777",
            email="smoke@example.com",
            address="Madhapur, Hyderabad",
            avg_surplus_kg="10-25 kg/day",
        )
    )
    assert registered.verification_status == "verified"

    linked_donor = store.update_donor_telegram(
        registered.id,
        DonorTelegramUpdate(
            telegram_chat_id="987654321",
            telegram_username="@smoke_kitchen",
            enabled=True,
        ),
    )
    assert linked_donor.telegram_enabled

    link = store.link_telegram_donor(
        TelegramLinkRequest(chat_id="123456789", fssai_license="13622011009876")
    )
    assert link.donor_id == "donor_hitech_banquet"

    telegram_result = store.create_telegram_donation(
        chat_id="123456789",
        caption="biryani 18kg, dal 6kg",
        photo_url="telegram_file_id_demo",
    )
    assert telegram_result.ok
    assert telegram_result.donation_id
    assert telegram_result.quantity_kg == 18

    message = store.create_message(
        CommunicationMessageCreate(
            donation_id=telegram_result.donation_id,
            sender_role=Role.ngo_coordinator,
            sender_id="ngo_city_meals",
            recipient_role=Role.donor,
            recipient_id=link.donor_id,
            body="We can pick this up in 25 minutes.",
        )
    )
    assert message.id
    assert store.list_notifications()
    assert store.list_messages(telegram_result.donation_id)

    impact = store.impact()
    assert impact.meals_served >= 87400
    assert store.predictions()

    print("Smoke flow passed: donation -> match -> accept -> complete -> impact -> emergency -> Telegram -> communications.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
