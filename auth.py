import hashlib
from database import Database


class UserAuth:
    """Handles user registration and login with SHA-256 password hashing."""

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = "pennypath_salt_2024"   # static salt (upgrade to bcrypt for production)
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

    def register(self, db: Database) -> dict | None:
        """Prompt for new credentials, create account. Returns user dict or None."""
        print("\n\033[32m─── REGISTER ───\033[0m")
        username = input("Choose a username: ").strip()
        if not username:
            print("\033[31mUsername cannot be empty.\033[0m")
            return None

        if db.get_user(username):
            print("\033[31mUsername already taken. Please try a different one.\033[0m")
            return None

        password = input("Choose a password: ").strip()
        if len(password) < 4:
            print("\033[31mPassword must be at least 4 characters.\033[0m")
            return None

        confirm = input("Confirm password: ").strip()
        if password != confirm:
            print("\033[31mPasswords do not match.\033[0m")
            return None

        pw_hash = self._hash_password(password)
        if db.create_user(username, pw_hash):
            row = db.get_user(username)
            print(f"\033[32m✔ Account created! Welcome, {username}!\033[0m")
            return {"id": row[0], "username": row[1]}
        else:
            print("\033[31mRegistration failed.\033[0m")
            return None

    def login(self, db: Database) -> dict | None:
        """Prompt for credentials. Returns user dict or None."""
        print("\n\033[32m─── LOGIN ───\033[0m")
        username = input("Username: ").strip()
        password = input("Password: ").strip()

        row = db.get_user(username)
        if row is None:
            print("\033[31mUser not found.\033[0m")
            return None

        pw_hash = self._hash_password(password)
        if pw_hash != row[2]:
            print("\033[31mIncorrect password.\033[0m")
            return None

        print(f"\033[32m✔ Welcome back, {username}!\033[0m")
        return {"id": row[0], "username": row[1]}


def login_screen(db: Database) -> dict:
    """Show login/register screen. Loops until successful. Returns user dict."""
    auth = UserAuth()
    while True:
        print("\n\033[32m╔══════════════════════╗\033[0m")
        print("\033[32m║ Welcome to PennyPath ║\033[0m")
        print("\033[32m╚══════════════════════╝\033[0m")
        print("1. Login")
        print("2. Register")
        print("0. Quit")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            user = auth.login(db)
            if user:
                return user
        elif choice == "2":
            user = auth.register(db)
            if user:
                return user
        elif choice == "0":
            print("Goodbye!")
            exit(0)
        else:
            print("\033[31mInvalid option.\033[0m")
