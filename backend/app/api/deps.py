"""Dependencies für Authentifizierung und Autorisierung."""
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User
from app.auth import verify_session_token, validate_csrf, generate_csrf_token


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Liest den authentifizierten Benutzer aus dem Cookie oder Authorization-Header."""
    token = request.cookies.get("tracced_session")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            
    if not token:
        return None
        
    user_id = verify_session_token(token)
    if not user_id:
        return None
        
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    
    # CSRF-Prüfung bei Cookie-basierter Auth und schreibenden Methoden
    if user and request.cookies.get("tracced_session"):
        validate_csrf(request, token)
        
    return user


async def get_current_user(
    current_user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """Erzwingt Authentifizierung; wirft 401 Unauthorized falls nicht eingeloggt."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht authentifiziert. Bitte einloggen."
        )
    return current_user
