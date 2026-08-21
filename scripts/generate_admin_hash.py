#!/usr/bin/env python3
"""Generate an Argon2id hash for ADMIN_PASSWORD_HASH without echoing the password."""

from getpass import getpass

from argon2 import PasswordHasher


password = getpass("Admin password: ")
confirmation = getpass("Confirm admin password: ")

if not password or password != confirmation:
    raise SystemExit("Passwords were empty or did not match.")

print(PasswordHasher().hash(password))