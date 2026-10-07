import os

from granian.constants import Interfaces
from granian.server import Server

import main_app


def load_dotenv() -> None:
    if not os.path.exists(".env"):
        return
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")
    print("[INFO] Loaded .env")


if __name__ == "__main__":
    args = main_app.parseArgs()
    load_dotenv()
    server = Server(
        target="main_app:app",
        address="0.0.0.0",
        port=args.port,
        interface=Interfaces.ASGI,
        workers=1,
        reload=False,
    )

    server.serve()
