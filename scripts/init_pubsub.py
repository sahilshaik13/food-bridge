import os
import sys

# Setup environment to import FastAPI app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from google.cloud import pubsub_v1
from app.core.cloud_clients import get_google_credentials
from app.core.config import get_settings

settings = get_settings()

if not settings.google_cloud_project:
    print("GOOGLE_CLOUD_PROJECT not set, skipping Pub/Sub topic creation.")
    sys.exit(0)

publisher = pubsub_v1.PublisherClient(credentials=get_google_credentials())

topics = ["foodbridge-donations", "foodbridge-emergencies"]
subscriptions = [
    ("foodbridge-donations", "foodbridge-donations-live-sub"),
    ("foodbridge-emergencies", "foodbridge-emergencies-live-sub"),
]

for topic_id in topics:
    topic_path = publisher.topic_path(settings.google_cloud_project, topic_id)
    try:
        publisher.create_topic(request={"name": topic_path})
        print(f"Created topic: {topic_path}")
    except Exception as e:
        if "AlreadyExists" in str(e) or "already exists" in str(e).lower():
            print(f"Topic {topic_path} already exists.")
        else:
            print(f"Failed to create topic {topic_path}: {e}")

subscriber = pubsub_v1.SubscriberClient(credentials=get_google_credentials())
for topic_id, sub_id in subscriptions:
    topic_path = publisher.topic_path(settings.google_cloud_project, topic_id)
    sub_path = subscriber.subscription_path(settings.google_cloud_project, sub_id)
    try:
        subscriber.create_subscription(
            request={
                "name": sub_path,
                "topic": topic_path,
                "ack_deadline_seconds": 30,
                "message_retention_duration": {"seconds": 86400},
            }
        )
        print(f"Created subscription: {sub_path} -> {topic_path}")
    except Exception as e:
        if "AlreadyExists" in str(e) or "already exists" in str(e).lower():
            print(f"Subscription {sub_path} already exists.")
        else:
            print(f"Failed to create subscription {sub_path}: {e}")

print("Pub/Sub topics initialization complete.")
