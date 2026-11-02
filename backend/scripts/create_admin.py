"""Crée le premier compte admin, directement en base.

Aucun endpoint HTTP ne crée de compte admin (ça ouvrirait une escalade de
privilèges) — ce script est la seule voie pour bootstrapper le tout premier
admin. Une fois celui-ci créé, les suivants (et les coiffeuses) se créent
via l'API, authentifié en admin.

Usage (depuis backend/, venv activé) :
    python scripts/create_admin.py --email admin@example.com --password "..."
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.models.enums import UserRole  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Crée un compte admin KYJA BEAUTÉ")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", default=None, help="Si omis, demandé de façon masquée")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Mot de passe (min. 10 caractères) : ")
    if len(password) < 10:
        print("Erreur : le mot de passe doit contenir au moins 10 caractères", file=sys.stderr)
        sys.exit(1)

    email = args.email.strip().lower()
    db = SessionLocal()
    try:
        user = User(email=email, password_hash=hash_password(password), role=UserRole.ADMIN, is_active=True)
        db.add(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        print(f"Erreur : un compte existe déjà avec l'email {email}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()

    print(f"Compte admin créé : {email}")


if __name__ == "__main__":
    main()
