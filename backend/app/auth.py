"""Sicherheit, Authentifizierung (Argon2id) und CSRF-Handling."""
import hmac
import hashlib
import secrets
import json
import base64
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError
from fastapi import Request, HTTPException, status
from app.config import settings

# Argon2id Hasher
ph = PasswordHasher(
    time_cost=3,        # 3 Iterationen
    memory_cost=65536,  # 64 MB
    parallelism=2,      # 2 Threads
    hash_len=32,
    type=Type.ID
)


def hash_password(password: str) -> str:
    """Erzeugt einen sicheren Argon2id-Hash."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifiziert ein Klartext-Passwort gegen den Argon2id-Hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def generate_csrf_token(session_id: str) -> str:
    """Erzeugt ein kryptographisch signiertes CSRF-Token für eine Sitzung."""
    message = f"csrf:{session_id}".encode()
    sig = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()
    return f"{sig[:32]}"


def create_session_token(user_id: uuid.UUID) -> str:
    """Erstellt ein signiertes Session-Token mit Ablaufzeitpunkt."""
    exp = int((datetime.now(timezone.utc) + timedelta(days=settings.SESSION_EXPIRE_DAYS)).timestamp())
    payload = {
        "uid": str(user_id),
        "exp": exp,
        "rnd": secrets.token_hex(8)
    }
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode()
    b64_payload = base64.urlsafe_b64encode(payload_bytes).decode().rstrip("=")
    
    signature = hmac.new(settings.SECRET_KEY.encode(), b64_payload.encode(), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{signature}"


def verify_session_token(token: str) -> Optional[uuid.UUID]:
    """Prüft die Signatur und das Verfallsdatum des Session-Tokens."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        b64_payload, signature = parts
        
        # Signatur prüfen
        expected_sig = hmac.new(settings.SECRET_KEY.encode(), b64_payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        
        # Padding ergänzen falls nötig
        rem = len(b64_payload) % 4
        padded = b64_payload + "=" * (4 - rem if rem > 0 else 0)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        
        # Ablaufdatum prüfen
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if data.get("exp", 0) < now_ts:
            return None
            
        return uuid.UUID(data["uid"])
    except Exception:
        return None


def validate_csrf(request: Request, session_token: str) -> None:
    """Validiert den X-CSRF-Token Header für modifizierende Anfragen."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    
    csrf_header = request.headers.get("X-CSRF-Token")
    if not csrf_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF-Token fehlt."
        )
    
    expected = generate_csrf_token(session_token)
    if not hmac.compare_digest(csrf_header, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ungültiges CSRF-Token."
        )
