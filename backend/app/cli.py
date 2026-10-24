"""CLI-Tool für administrative Aufgaben (z.B. Benutzer anlegen)."""
import sys
import asyncio
import argparse
from sqlalchemy import select
from app.database import AsyncSessionLocal, engine, Base
from app.models import User
from app.auth import hash_password


async def init_db():
    """Erstellt alle Datenbanktabellen (falls noch nicht vorhanden)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def create_user(email: str, password: str):
    """Erstellt einen neuen Benutzer in der Datenbank."""
    await init_db()
    async with AsyncSessionLocal() as session:
        # Prüfen ob E-Mail existiert
        res = await session.execute(select(User).where(User.email == email.strip().lower()))
        if res.scalar_one_or_none():
            print(f"Fehler: Ein Benutzer mit der E-Mail '{email}' existiert bereits.")
            sys.exit(1)
            
        hashed = hash_password(password)
        new_user = User(
            email=email.strip().lower(),
            hashed_password=hashed,
            is_active=True
        )
        session.add(new_user)
        await session.commit()
        print(f"Benutzer '{email}' erfolgreich angelegt (ID: {new_user.id}).")


def main():
    parser = argparse.ArgumentParser(description="Tracced CLI Administration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Befehl: create-user
    user_parser = subparsers.add_parser("create-user", help="Erstellt einen neuen Benutzer")
    user_parser.add_argument("--email", required=True, help="E-Mail-Adresse")
    user_parser.add_argument("--password", required=True, help="Sicheres Passwort (mind. 8 Zeichen)")

    # Befehl: init-db
    subparsers.add_parser("init-db", help="Erstellt das Datenbankschema")

    args = parser.parse_args()

    if args.command == "create-user":
        if len(args.password) < 8:
            print("Fehler: Das Passwort muss mindestens 8 Zeichen lang sein.")
            sys.exit(1)
        asyncio.run(create_user(args.email, args.password))
    elif args.command == "init-db":
        asyncio.run(init_db())
        print("Datenbankschema erfolgreich initialisiert.")


if __name__ == "__main__":
    main()
