import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.redis_client import get_redis
from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, decode_access_token
from app.database import get_db
from app.models import Client, User
from app.models.enums import UserRole

_bearer_scheme = HTTPBearer(auto_error=False)

LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 15 * 60


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Identifiants invalides ou expirés",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized

    try:
        payload = decode_access_token(creds.credentials)
    except JWTError:
        raise unauthorized

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise unauthorized

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized

    return user


def require_role(*roles: UserRole):
    def _checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé")
        return current_user

    return _checker


def get_current_client(current_user: User = Depends(require_role(UserRole.CLIENT))) -> Client:
    """Centralise la navigation User -> Client pour les routes réservées aux
    clientes (ex: réservation)."""
    client_profile = current_user.client
    if client_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profil client introuvable")
    return client_profile


def verify_csrf(request: Request) -> None:
    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    header_value = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_value or not header_value or cookie_value != header_value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Vérification CSRF échouée")


def _login_rate_limit_key(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"ratelimit:login:{ip}"


def login_rate_limiter(request: Request) -> None:
    redis_client = get_redis()
    key = _login_rate_limit_key(request)

    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)

    if count > LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
        ttl = redis_client.ttl(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives, réessayez plus tard",
            headers={"Retry-After": str(max(ttl, 1))},
        )


def clear_login_rate_limit(request: Request) -> None:
    """À appeler après un login réussi pour ne pas pénaliser l'utilisateur
    pour des tentatives précédentes une fois qu'il a fini par réussir."""
    get_redis().delete(_login_rate_limit_key(request))
