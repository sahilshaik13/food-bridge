from __future__ import annotations

from functools import lru_cache
from typing import Any

from google.oauth2 import service_account

from app.core.config import Settings, get_settings


@lru_cache
def get_google_credentials() -> Any:
    settings = get_settings()
    if settings.google_application_credentials:
        return service_account.Credentials.from_service_account_file(
            str(settings.google_application_credentials)
        )
    return None  # Let the SDK discover credentials automatically


@lru_cache
def initialize_firebase_app() -> Any:
    """Initialize Firebase Admin against the Firebase project only."""

    import firebase_admin
    from firebase_admin import credentials

    settings = get_settings()
    existing = firebase_admin.get_app() if firebase_admin._apps else None
    if existing:
        return existing

    if settings.firebase_admin_credentials:
        firebase_credential = credentials.Certificate(str(settings.firebase_admin_credentials))
    else:
        # Use Application Default Credentials (ADC) in production
        firebase_credential = credentials.ApplicationDefault()

    return firebase_admin.initialize_app(
        firebase_credential,
        {
            "projectId": settings.firebase_project_id,
            "databaseURL": settings.firebase_database_url,
            "storageBucket": settings.firebase_storage_bucket,
        },
    )


def get_firestore_client() -> Any:
    from firebase_admin import firestore

    initialize_firebase_app()
    return firestore.client()


def get_realtime_database() -> Any:
    from firebase_admin import db

    initialize_firebase_app()
    return db.reference("/")


def get_firebase_storage_bucket() -> Any:
    from firebase_admin import storage

    initialize_firebase_app()
    return storage.bucket()


def get_gcp_storage_client() -> Any:
    from google.cloud import storage

    settings = get_settings()
    return storage.Client(
        project=settings.google_cloud_project,
        credentials=get_google_credentials(),
    )


def ensure_bucket_exists(bucket_name: str) -> Any:
    client = get_gcp_storage_client()
    bucket = client.bucket(bucket_name)
    if not bucket.exists():
        print(f"Creating bucket: {bucket_name}")
        bucket = client.create_bucket(bucket_name, location=get_settings().gcp_location)
    return bucket


def get_firebase_auth() -> Any:
    from firebase_admin import auth

    initialize_firebase_app()
    return auth


def get_bigquery_client() -> Any:
    from google.cloud import bigquery

    settings = get_settings()
    return bigquery.Client(
        project=settings.google_cloud_project,
        credentials=get_google_credentials(),
    )


def get_pubsub_publisher() -> Any:
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient(credentials=get_google_credentials())


def get_cloud_tasks_client() -> Any:
    from google.cloud import tasks_v2

    return tasks_v2.CloudTasksClient(credentials=get_google_credentials())


def get_secret_manager_client() -> Any:
    from google.cloud import secretmanager

    return secretmanager.SecretManagerServiceClient(credentials=get_google_credentials())


def initialize_vertex_ai(settings: Settings | None = None) -> bool:
    import vertexai

    settings = settings or get_settings()
    vertexai.init(
        project=settings.google_cloud_project,
        location=settings.gcp_location,
        credentials=get_google_credentials(),
    )
    return True
