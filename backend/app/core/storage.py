from abc import ABC, abstractmethod
from pathlib import Path

from app.config import settings


class StorageBackend(ABC):
    @abstractmethod
    def save(self, data: bytes, key: str, content_type: str) -> str:
        """Enregistre `data` sous `key`, retourne une URL publique."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Supprime le fichier `key`. Ne lève pas si déjà absent."""


class LocalStorageBackend(StorageBackend):
    """Stockage sur disque local. Interchangeable avec un futur R2StorageBackend
    (boto3) implémentant la même interface — seul get_storage() changerait."""

    def __init__(self, base_dir: Path, base_url: str = "/media"):
        self.base_dir = base_dir
        self.base_url = base_url.rstrip("/")

    def save(self, data: bytes, key: str, content_type: str) -> str:
        path = self.base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"{self.base_url}/{key}"

    def delete(self, key: str) -> None:
        path = self.base_dir / key
        path.unlink(missing_ok=True)

    def key_from_url(self, url: str) -> str | None:
        prefix = f"{self.base_url}/"
        if url.startswith(prefix):
            return url[len(prefix):]
        return None


def get_storage() -> LocalStorageBackend:
    return LocalStorageBackend(base_dir=Path(settings.LOCAL_STORAGE_DIR))
