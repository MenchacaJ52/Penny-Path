"""
Password hashing and login shared by the CLI, desktop app, and web app.

New passwords use Werkzeug's salted scrypt hashes. Accounts created before that
used an unsalted-per-user SHA-256 hash; those still log in, and are transparently
upgraded to scrypt on their next successful login.
"""
import hashlib
import hmac
from getpass import getpass

from werkzeug.security import check_password_hash, generate_password_hash

from pennypath.database import Database

MIN_PASSWORD_LEN = 8
_LEGACY_SALT = "pennypath_salt_2024"
LOGIN_FAILED = "Invalid username or password."   # same message either way: no username probing


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def _is_legacy(stored_hash: str) -> bool:
    return ":" not in stored_hash   # werkzeug hashes look like "scrypt:32768:8:1$salt$hash"


def verify_password(password: str, stored_hash: str) -> bool:
    if _is_legacy(stored_hash):
        legacy = hashlib.sha256(f"{_LEGACY_SALT}{password}".encode()).hexdigest()
        return hmac.compare_digest(legacy, stored_hash)
    return check_password_hash(stored_hash, password)


def validate_new_password(password: str, confirm: str) -> str | None:
    """Return an error message, or None if the new password is acceptable."""
    if len(password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    if password != confirm:
        return "Passwords do not match."
    return None


def authenticate(db: Database, username: str, password: str) -> dict | None:
    """Return {"id", "username", "onboarded"} on success, else None.
    Upgrades legacy SHA-256 hashes to scrypt on a successful login."""
    row = db.get_user(username)
    if row is None or not verify_password(password, row[2]):
        return None
    if _is_legacy(row[2]):
        db.update_password(row[0], hash_password(password))
    return {"id": row[0], "username": row[1], "onboarded": bool(row[3])}


def register(db: Database, username: str, password: str, confirm: str) -> tuple[dict | None, str | None]:
    """Create an account. Returns (user, None) on success or (None, error message)."""
    username = username.strip()
    if not username:
        return None, "Username cannot be empty."
    if len(username) > 50:
        return None, "Username must be 50 characters or fewer."
    error = validate_new_password(password, confirm)
    if error:
        return None, error
    if not db.create_user(username, hash_password(password)):
        return None, "Username already taken."
    row = db.get_user(username)
    return {"id": row[0], "username": row[1], "onboarded": bool(row[3])}, None


# ── CLI screens ───────────────────────────────────────────────────────────────

def _cli_register(db: Database) -> dict | None:
    print("\n\033[32m─── REGISTER ───\033[0m")
    username = input("Choose a username: ")
    password = getpass(f"Choose a password ({MIN_PASSWORD_LEN}+ characters): ")
    confirm = getpass("Confirm password: ")
    user, error = register(db, username, password, confirm)
    if error:
        print(f"\033[31m{error}\033[0m")
        return None
    print(f"\033[32m✔ Account created! Welcome, {user['username']}!\033[0m")
    return user


def _cli_login(db: Database) -> dict | None:
    print("\n\033[32m─── LOGIN ───\033[0m")
    username = input("Username: ").strip()
    password = getpass("Password: ")
    user = authenticate(db, username, password)
    if user is None:
        print(f"\033[31m{LOGIN_FAILED}\033[0m")
        return None
    print(f"\033[32m✔ Welcome back, {username}!\033[0m")
    return user


def login_screen(db: Database) -> dict:
    """Show login/register screen. Loops until successful. Returns user dict."""
    while True:
        print("\n\033[32m╔══════════════════════╗\033[0m")
        print("\033[32m║ Welcome to PennyPath ║\033[0m")
        print("\033[32m╚══════════════════════╝\033[0m")
        print("1. Login")
        print("2. Register")
        print("0. Quit")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            user = _cli_login(db)
            if user:
                return user
        elif choice == "2":
            user = _cli_register(db)
            if user:
                return user
        elif choice == "0":
            print("Goodbye!")
            raise SystemExit(0)
        else:
            print("\033[31mInvalid option.\033[0m")
