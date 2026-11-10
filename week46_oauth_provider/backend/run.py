"""Server entrypoint for PulseAuth OAuth 2.0 / OIDC Identity Provider."""

import os
import sys
from pathlib import Path

# Ensure backend package is in python search path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from app import create_app  # noqa: E402
from app.config.settings import get_config  # noqa: E402
from data.seed import seed_database  # noqa: E402

config = get_config()
app = create_app(config)

if __name__ == "__main__":
    db_path = app.config.get("DATABASE_PATH")
    if db_path and db_path != ":memory:":
        seed_database(db_path)

    port = int(os.getenv("PORT", "5000"))
    print(f"[PulseAuth Identity Provider] Server listening on http://127.0.0.1:{port}")
    print(f"[PulseAuth Identity Provider] Issuer: {app.config.get('ISSUER')}")
    print(
        "[PulseAuth Identity Provider] OpenID Discovery: "
        "/.well-known/openid-configuration"
    )
    print("[PulseAuth Identity Provider] JWKS Keyset: /.well-known/jwks.json")

    app.run(host="0.0.0.0", port=port, debug=config.DEBUG)
