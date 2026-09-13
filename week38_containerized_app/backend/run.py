"""Application entry point for Docker Pulse Task and Ops Hub."""

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    host = os.getenv("HOST", "0.0.0.0")
    debug = app.config.get("DEBUG", False)
    app.run(host=host, port=port, debug=debug)
