from cryptography.fernet import Fernet
from django.conf import settings


class EncryptionService:
    def __init__(self):
        key = settings.AI_CONFIG_ENCRYPTION_KEY.encode()
        self._fernet = Fernet(key)

    def encrypt(self, plain_text: str) -> str:
        return self._fernet.encrypt(plain_text.encode()).decode()

    def decrypt(self, encrypted_text: str) -> str:
        return self._fernet.decrypt(encrypted_text.encode()).decode()


_encryption_service = None


def get_encryption():
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service
