from app.core.cloud_clients import initialize_firebase_app
from app.models import Role


def send_fcm_notification(token: str, title: str, body: str, data: dict | None = None):
    """Send a real FCM push notification using Firebase Admin SDK."""
    app = initialize_firebase_app()
    if app is None:
        raise RuntimeError("Firebase not initialized")

    from firebase_admin import messaging
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data or {},
        token=token,
    )

    try:
        response = messaging.send(message)
        print(f"Successfully sent FCM message: {response}")
        return response
    except Exception as e:
        print(f"Error sending FCM message: {e}")
        return None


def notify_ngo_of_donation(ngo_token: str, donation_id: str, donor_name: str, food_type: str):
    title = "New Food Surplus Available!"
    body = f"{donor_name} has {food_type} ready for pickup."
    data = {
        "donation_id": donation_id,
        "type": "NEW_DONATION"
    }
    return send_fcm_notification(ngo_token, title, body, data)
