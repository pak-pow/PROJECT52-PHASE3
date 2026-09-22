from app import create_app
from app.config.settings import get_config

config = get_config()
app = create_app(config)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
