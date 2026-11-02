from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import clear_login_rate_limit, get_current_user, login_rate_limiter, verify_csrf
from app.core.security import (
    CSRF_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    create_access_token,
    generate_csrf_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.database import get_db
from app.models import Client, ConsentRecord, RefreshToken, User
from app.models.enums import ConsentType, UserRole
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    UserPublic,
)

router = APIRouter()
logger = structlog.get_logger()


def _cookie_security_flags() -> dict:
    if settings.ENVIRONMENT == "production":
        return {"secure": True, "samesite": "none"}
    return {"secure": False, "samesite": "lax"}


def _set_auth_cookies(response: Response, raw_refresh_token: str, csrf_token: str) -> None:
    flags = _cookie_security_flags()
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh_token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        **flags,
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        httponly=False,
        **flags,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
    response.delete_cookie(key=CSRF_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> RegisterResponse:
    user = User(email=payload.email, password_hash=hash_password(payload.password), role=UserRole.CLIENT, is_active=True)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un compte existe déjà avec cet email")

    client = Client(
        user_id=user.id,
        nom=payload.nom,
        prenom=payload.prenom,
        telephone=payload.telephone,
        adresse=payload.adresse,
        date_naissance=payload.date_naissance,
    )
    db.add(client)
    db.flush()

    now = datetime.now(timezone.utc)
    ip_address = request.client.host if request.client else None
    db.add_all(
        [
            ConsentRecord(
                client_id=client.id,
                consent_type=ConsentType.TERMS_OF_SERVICE,
                granted=True,
                granted_at=now,
                ip_address=ip_address,
            ),
            ConsentRecord(
                client_id=client.id,
                consent_type=ConsentType.MARKETING,
                granted=payload.marketing_opt_in,
                granted_at=now,
                ip_address=ip_address,
            ),
        ]
    )
    db.commit()

    return RegisterResponse(id=user.id, email=user.email)


@router.post("/login", response_model=LoginResponse, dependencies=[Depends(login_rate_limiter)])
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password_hash):
        logger.warning("login_failed", email=payload.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou mot de passe incorrect")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Compte désactivé")

    clear_login_rate_limit(request)

    raw_refresh_token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()

    _set_auth_cookies(response, raw_refresh_token, generate_csrf_token())

    return LoginResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserPublic.model_validate(user),
    )


@router.post("/refresh", response_model=RefreshResponse, dependencies=[Depends(verify_csrf)])
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> RefreshResponse:
    # NOTE: on ne tente pas de clear les cookies dans les branches d'erreur ci-dessous :
    # une exception levée après avoir muté `response` construit une toute nouvelle
    # réponse côté FastAPI/Starlette, donc toute mutation de `response` avant un
    # `raise` est silencieusement perdue — un cookie périmé est de toute façon
    # inoffensif, il expirera naturellement ou échouera au prochain refresh.
    raw_refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expirée")

    token_hash = hash_refresh_token(raw_refresh_token)
    row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expirée")

    now = datetime.now(timezone.utc)

    if row.revoked_at is not None:
        # Rejeu d'un token déjà rotaté = signal de vol : on révoque tout pour cet utilisateur.
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalide, veuillez vous reconnecter")

    if row.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expirée")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Compte désactivé")

    row.revoked_at = now
    new_raw_refresh_token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(new_raw_refresh_token),
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()

    _set_auth_cookies(response, new_raw_refresh_token, generate_csrf_token())

    return RefreshResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserPublic.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    raw_refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_refresh_token:
        db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == hash_refresh_token(raw_refresh_token),
                RefreshToken.user_id == current_user.id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        db.commit()

    _clear_auth_cookies(response)


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)
