"""Authentifizierungs-Routen (Login, Logout, Session-Status)."""
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, AuthStatus, UserRead
from app.auth import verify_password, create_session_token, generate_csrf_token
from app.api.deps import get_current_user_optional
from app.config import settings

router = APIRouter(prefix="/auth", tags=["Authentifizierung"])


@router.post("/login", response_model=AuthStatus)
async def login(
    credentials: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """Prüft Anmeldedaten und setzt das HttpOnly Session-Cookie."""
    result = await db.execute(select(User).where(User.email == credentials.email.lower()))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige E-Mail-Adresse oder Passwort."
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dieser Benutzer-Account ist deaktiviert."
        )
        
    session_token = create_session_token(user.id)
    csrf_token = generate_csrf_token(session_token)
    
    # Cookie setzen (HttpOnly, konfigurierbares Secure & SameSite)
    response.set_cookie(
        key="tracced_session",
        value=session_token,
        max_age=settings.SESSION_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=settings.SECURE_COOKIES,
        samesite=settings.COOKIE_SAMESITE,
        path="/"
    )
    
    return AuthStatus(
        authenticated=True,
        user=UserRead.model_validate(user),
        csrf_token=csrf_token
    )


@router.post("/logout")
async def logout(response: Response):
    """Beendet die Sitzung und löscht das Cookie."""
    response.delete_cookie(key="tracced_session", path="/")
    return {"message": "Erfolgreich abgemeldet."}


@router.get("/status", response_model=AuthStatus)
async def auth_status(
    request: Request,
    current_user = Depends(get_current_user_optional)
):
    """Liefert den aktuellen Anmeldestatus und das zugehörige CSRF-Token."""
    if not current_user:
        return AuthStatus(authenticated=False, user=None, csrf_token=None)
        
    token = request.cookies.get("tracced_session")
    csrf_token = generate_csrf_token(token) if token else None
    
    return AuthStatus(
        authenticated=True,
        user=UserRead.model_validate(current_user),
        csrf_token=csrf_token
    )
