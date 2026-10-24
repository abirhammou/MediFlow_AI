import asyncio
import getpass
import sys
from datetime import UTC, datetime
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.config import settings
from app.security import hash_password


async def seed_admin() -> None:
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        database = client[settings.mongo_db]
        users = database["users"]
        await users.create_index("email", unique=True, name="email_unique")

        existing_admin = await users.find_one({"role": "admin"})
        if existing_admin is not None:
            print(f"Un administrateur existe déjà : {existing_admin['email']}")
            return

        configured_email = settings.admin_email or ""
        email = (configured_email.strip() or input("Email de l'admin : ")).strip().lower()
        configured_password = settings.admin_password or ""
        password = configured_password or getpass.getpass("Mot de passe de l'admin : ")

        if len(password) < 8:
            raise ValueError("Le mot de passe doit faire au moins 8 caractères.")
        if not email:
            raise ValueError("L'adresse email est obligatoire.")

        user = {
            "email": email,
            "full_name": "Administrateur",
            "password_hash": hash_password(password),
            "role": "admin",
            "status": "active",
            "patient_id": None,
            "created_at": datetime.now(UTC),
        }
        result = await users.insert_one(user)
        print(f"Admin créé avec succès : {email} (id: {result.inserted_id})")
    finally:
        client.close()


if __name__ == "__main__":
    try:
        asyncio.run(seed_admin())
    except (ValueError, KeyboardInterrupt) as exc:
        print(f"Création de l'admin annulée : {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
