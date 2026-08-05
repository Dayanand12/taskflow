#!/usr/bin/env python3
"""
Manage the single password used to lock notes in TaskFlow.

The password is never stored in plaintext -- only a salted PBKDF2-SHA256 hash
lives in the database (table `note_lock`), so it cannot be "recovered" or
displayed, only verified against a guess or replaced with a new one. This
script is the supported way to set it up, change it, or reset it if it's
been forgotten, without going through the app's UI.

Usage (run from anywhere; the DB path is auto-detected next to this script):
    python scripts/notes_password.py status
    python scripts/notes_password.py set
    python scripts/notes_password.py change
    python scripts/notes_password.py reset
    python scripts/notes_password.py unlock-all

Flags:
    --db PATH     Use a specific tasks.db instead of the auto-detected one.
    --password    Supply the password inline instead of an interactive
                  (hidden) prompt -- handy for scripting, but be aware it may
                  land in your shell history.
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from notes_auth import hash_password, verify_password  # noqa: E402

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "tasks.db"


def get_conn(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        print(f"Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS note_lock ("
        " id INTEGER PRIMARY KEY CHECK (id = 1),"
        " password_hash TEXT NOT NULL,"
        " salt TEXT NOT NULL,"
        " updated_at TEXT NOT NULL"
        ")"
    )
    return conn


def get_lock_row(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM note_lock WHERE id=1").fetchone()


def prompt_password(label="Password", confirm=False) -> str:
    pw = getpass(f"{label}: ")
    if not pw:
        print("Password cannot be empty.", file=sys.stderr)
        sys.exit(1)
    if len(pw) < 4:
        print("Password must be at least 4 characters.", file=sys.stderr)
        sys.exit(1)
    if confirm:
        pw2 = getpass("Confirm password: ")
        if pw != pw2:
            print("Passwords did not match.", file=sys.stderr)
            sys.exit(1)
    return pw


def cmd_status(conn: sqlite3.Connection, args):
    row = get_lock_row(conn)
    locked_count = conn.execute(
        "SELECT COUNT(*) FROM note_pages WHERE is_locked=1"
    ).fetchone()[0]
    if not row:
        print("No notes password is configured yet. Run 'set' to create one.")
    else:
        print(f"Notes password configured.  Last changed: {row['updated_at']}")
    print(f"Locked notes: {locked_count}")


def cmd_set(conn: sqlite3.Connection, args):
    if get_lock_row(conn) and not args.force:
        print(
            "A notes password is already set. Use 'change' (if you know the current "
            "one) or 'reset' (if you don't), or pass --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)
    pw = args.password or prompt_password("New password", confirm=True)
    pw_hash, salt = hash_password(pw)
    conn.execute(
        "INSERT INTO note_lock (id,password_hash,salt,updated_at) VALUES (1,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET password_hash=excluded.password_hash, "
        "salt=excluded.salt, updated_at=excluded.updated_at",
        (pw_hash, salt, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    print("Notes password set.")


def cmd_change(conn: sqlite3.Connection, args):
    row = get_lock_row(conn)
    if not row:
        print("No notes password is set yet -- use 'set' instead.", file=sys.stderr)
        sys.exit(1)
    old_pw = args.old_password or getpass("Current password: ")
    if not verify_password(old_pw, row["password_hash"], row["salt"]):
        print("Current password is incorrect.", file=sys.stderr)
        sys.exit(1)
    new_pw = args.password or prompt_password("New password", confirm=True)
    pw_hash, salt = hash_password(new_pw)
    conn.execute(
        "UPDATE note_lock SET password_hash=?, salt=?, updated_at=? WHERE id=1",
        (pw_hash, salt, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    print("Notes password changed.")


def cmd_reset(conn: sqlite3.Connection, args):
    """Forgot-password recovery: overwrite the hash without knowing the old one.
    Locked notes stay locked -- their content is untouched -- you'll just unlock
    them with the new password afterwards."""
    if not get_lock_row(conn):
        print("No notes password is set yet -- use 'set' instead.", file=sys.stderr)
        sys.exit(1)
    if not args.yes:
        answer = input(
            "This resets the notes password without knowing the old one "
            "(anyone with access to this machine could do this -- it's meant for "
            "when you've forgotten it yourself). Type RESET to confirm: "
        )
        if answer != "RESET":
            print("Aborted.")
            sys.exit(1)
    new_pw = args.password or prompt_password("New password", confirm=True)
    pw_hash, salt = hash_password(new_pw)
    conn.execute(
        "UPDATE note_lock SET password_hash=?, salt=?, updated_at=? WHERE id=1",
        (pw_hash, salt, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    print("Notes password reset. Locked notes are unchanged and now use the new password.")


def cmd_unlock_all(conn: sqlite3.Connection, args):
    """Emergency escape hatch: strip the lock flag from every note (content is
    never touched), for when the password is unrecoverable and you just want
    your notes back."""
    if not args.yes:
        answer = input(
            f"This removes password protection from ALL locked notes. Type UNLOCK to confirm: "
        )
        if answer != "UNLOCK":
            print("Aborted.")
            sys.exit(1)
    n = conn.execute("SELECT COUNT(*) FROM note_pages WHERE is_locked=1").fetchone()[0]
    conn.execute("UPDATE note_pages SET is_locked=0")
    conn.commit()
    print(f"Removed the lock from {n} note(s).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to tasks.db")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show whether a notes password is configured")

    p_set = sub.add_parser("set", help="Set the notes password for the first time")
    p_set.add_argument("--password", help="Password (omit to be prompted, hidden)")
    p_set.add_argument("--force", action="store_true", help="Overwrite an existing password without the old one")

    p_change = sub.add_parser("change", help="Change the password (requires the current one)")
    p_change.add_argument("--old-password", help="Current password (omit to be prompted, hidden)")
    p_change.add_argument("--password", help="New password (omit to be prompted, hidden)")

    p_reset = sub.add_parser("reset", help="Forgot the password? Overwrite it without the old one")
    p_reset.add_argument("--password", help="New password (omit to be prompted, hidden)")
    p_reset.add_argument("-y", "--yes", action="store_true", help="Skip the confirmation prompt")

    p_unlock = sub.add_parser("unlock-all", help="Remove the lock from every note (content untouched)")
    p_unlock.add_argument("-y", "--yes", action="store_true", help="Skip the confirmation prompt")

    args = parser.parse_args()
    conn = get_conn(args.db)
    try:
        {
            "status": cmd_status,
            "set": cmd_set,
            "change": cmd_change,
            "reset": cmd_reset,
            "unlock-all": cmd_unlock_all,
        }[args.command](conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
