import os
from app import create_app
from app.config.settings import get_config

config = get_config(os.getenv("FLASK_ENV", "development"))
app = create_app(config)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 [CI/CD Monitor Service] Starting server on http://127.0.0.1:{port} ({config.ENV})")
    app.run(host="0.0.0.0", port=port, debug=config.DEBUG)
