"""Database seeding utility for PulseAuth demo users and registered clients."""

import sqlite3
import sys
from pathlib import Path
from typing import Optional

# Ensure backend package is in python search path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.connection import init_db  # noqa: E402
from app.models.client_model import ClientModel  # noqa: E402
from app.models.user_model import UserModel  # noqa: E402


def seed_database(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Populate database with demo users, public and confidential clients."""
    conn = init_db(db_path)

    # 1. Seed demo users
    demo_users = [
        ("developer@pulseauth.dev", "DevPass2026!", "Alice Dev"),
        ("admin@pulseauth.dev", "AdminPass2026!", "Bob Admin"),
        ("user@pulseauth.dev", "UserPass2026!", "Charlie User"),
    ]

    for email, password, full_name in demo_users:
        existing = UserModel.get_by_email(conn, email)
        if not existing:
            UserModel.create(conn, email, password, full_name, is_active=True)
            print(f"[SEED] Created user: {email}")

    # 2. Seed demo OAuth 2.0 clients
    demo_clients = [
        {
            "client_id": "pulse-web-app",
            "client_name": "PulseWeb Portal (Confidential)",
            "client_type": "confidential",
            "client_secret": "pulse_web_secret_2026",
            "redirect_uris": [
                "http://127.0.0.1:3000/callback",
                "http://localhost:3000/callback",
            ],
            "grant_types": ["authorization_code", "refresh_token"],
            "scopes": [
                "openid",
                "profile",
                "email",
                "offline_access",
                "read:documents",
                "write:documents",
            ],
        },
        {
            "client_id": "pulse-mobile-app",
            "client_name": "PulseMobile Native Client (Public PKCE)",
            "client_type": "public",
            "client_secret": None,
            "redirect_uris": [
                "http://127.0.0.1:3000/callback",
                "http://localhost:3000/callback",
                "com.pulseauth.app://callback",
            ],
            "grant_types": ["authorization_code", "refresh_token"],
            "scopes": [
                "openid",
                "profile",
                "email",
                "offline_access",
                "read:documents",
            ],
        },
        {
            "client_id": "pulse-m2m-service",
            "client_name": "Pulse Analytics Microservice (Machine-to-Machine)",
            "client_type": "confidential",
            "client_secret": "pulse_m2m_secret_2026",
            "redirect_uris": [],
            "grant_types": ["client_credentials"],
            "scopes": ["read:documents", "write:documents"],
        },
    ]

    for client in demo_clients:
        existing = ClientModel.get_by_client_id(conn, client["client_id"])
        if not existing:
            ClientModel.create(
                conn=conn,
                client_id=client["client_id"],
                client_name=client["client_name"],
                client_type=client["client_type"],
                client_secret=client["client_secret"],
                redirect_uris=client["redirect_uris"],
                grant_types=client["grant_types"],
                scopes=client["scopes"],
            )
            cid = client["client_id"]
            ctype = client["client_type"]
            print(f"[SEED] Registered client: {cid} ({ctype})")

    print("[SEED] Database seeding complete.")
    return conn


if __name__ == "__main__":
    db_file = str(BACKEND_DIR / "data" / "pulse_auth.db")
    seed_database(db_file)
