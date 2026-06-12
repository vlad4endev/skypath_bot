#!/usr/bin/env python3
"""Generate ADMIN_PASSWORD hash for .env file.

Usage:
  python3 scripts/gen_admin_password.py "your-secure-password"
  python3 scripts/gen_admin_password.py "your-secure-password" --salt "custom-salt"

On server (inside Docker):
  docker compose exec bot python scripts/gen_admin_password.py "your-secure-password"
"""
import argparse
import hashlib
import os


def digest(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Generate ADMIN_PASSWORD for .env")
    parser.add_argument("password", help="Plain-text admin password")
    parser.add_argument("--salt", default="", help="Salt (default: WEBHOOK_SECRET or fallback)")
    args = parser.parse_args()

    salt = args.salt or os.getenv("WEBHOOK_SECRET", "")[:32] or "skypath-admin-salt"
    hashed = digest(args.password, salt)

    print(f"ADMIN_PASSWORD={hashed}")
    print(f"ADMIN_PASSWORD_SALT={salt}")
    print()
    print("Add these lines to your .env file.")


if __name__ == "__main__":
    main()
