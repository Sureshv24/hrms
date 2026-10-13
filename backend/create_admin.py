
from getpass import getpass

from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.user import User


def main():
    db = SessionLocal()

    try:
        email = input("Admin email: ").strip().lower()
        full_name = input("Admin full name: ").strip()
        password = getpass("Admin password (minimum 8 characters): ")

        if not full_name or len(password) < 8:
            print("Name is required and password must have at least 8 characters.")
            return

        existing = db.query(User).filter(User.email == email).first()

        if existing:
            print("This email already exists. No changes were made.")
            print("Use a separate trusted account for Admin provisioning.")
            return

        admin = User(
            full_name=full_name,
            email=email,
            hashed_password=hash_password(password),
            role="Admin",
            is_active=True,
        )

        db.add(admin)
        db.commit()

        print("Admin account created successfully.")

    except Exception as exc:
        db.rollback()
        print("Admin creation failed:", exc)

    finally:
        db.close()


if __name__ == "__main__":
    main()
