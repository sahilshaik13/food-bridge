import base64
from app.core.config import get_settings

try:
    from google.cloud import kms_v1
except ImportError:  # pragma: no cover - local fallback when dependency is missing
    kms_v1 = None

class KmsService:
    def __init__(self):
        self.settings = get_settings()
        self.client = None
        self.key_name = None
        if kms_v1 is not None:
            self.client = kms_v1.KeyManagementServiceClient()
            self.key_name = self.client.crypto_key_path(
                self.settings.google_cloud_project,
                self.settings.kms_location,
                self.settings.kms_keyring,
                self.settings.kms_key_name,
            )

    def encrypt(self, plaintext: str) -> str:
        """Encrypts a string and returns a base64 encoded ciphertext."""
        if not plaintext:
            return ""
        if self.client is None or self.key_name is None:
            # Local/dev fallback to avoid crashing when KMS package is unavailable.
            return plaintext

        response = self.client.encrypt(
            request={
                "name": self.key_name,
                "plaintext": plaintext.encode("utf-8")
            }
        )
        return base64.b64encode(response.ciphertext).decode("utf-8")

    def decrypt(self, ciphertext_b64: str) -> str:
        """Decrypts a base64 encoded ciphertext and returns the original string."""
        if not ciphertext_b64:
            return ""
        if self.client is None or self.key_name is None:
            return ciphertext_b64

        try:
            ciphertext = base64.b64decode(ciphertext_b64)
            response = self.client.decrypt(
                request={
                    "name": self.key_name,
                    "ciphertext": ciphertext
                }
            )
            return response.plaintext.decode("utf-8")
        except Exception:
            # Supports legacy/plain tokens that were stored before KMS was available.
            return ciphertext_b64

kms_service = KmsService()
