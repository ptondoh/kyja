from cryptography.fernet import Fernet
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.config import settings

_fernet = Fernet(settings.ENCRYPTION_KEY.encode())


class EncryptedString(TypeDecorator):
    """Chiffrement transparent (Fernet) des champs sensibles stockés en base.

    Le code applicatif lit/écrit du texte en clair ; la colonne stocke le
    ciphertext base64. Pas de longueur fixe (impl=Text) car l'overhead
    Fernet (IV + HMAC + base64) varie selon la longueur de la valeur.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _fernet.decrypt(value.encode("utf-8")).decode("utf-8")
