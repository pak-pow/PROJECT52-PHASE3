import os
from app import create_app
from data.seed import seed_database

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        seed_database()

    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False)
