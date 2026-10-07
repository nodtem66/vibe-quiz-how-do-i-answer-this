import os
import re
import shutil
import subprocess
import threading

from granian.constants import Interfaces
from granian.server import Server

import main_app


def start_cloudflared(
    port: int,
) -> tuple[subprocess.Popen | None, threading.Event]:
    tunnel_ready = threading.Event()
    cloudflared = shutil.which("cloudflared")
    if cloudflared is None:
        print("[WARNING] cloudflared is not installed; using local URLs only.")
        return None, tunnel_ready

    try:
        version = subprocess.run(
            [cloudflared, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"[INFO] {version.stdout.strip() or version.stderr.strip()}")
        process = subprocess.Popen(
            [cloudflared, "tunnel", "--url", f"http://localhost:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        def print_tunnel_url() -> None:
            if process.stdout is None:
                return
            for line in process.stdout:
                match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if match:
                    tunnel_url = match.group(0)
                    print(f"[INFO] Tunnel player URL: {tunnel_url}")
                    os.environ["PLAYER_URL"] = tunnel_url
                    tunnel_ready.set()
                    break

        threading.Thread(target=print_tunnel_url, daemon=True).start()
        return process, tunnel_ready
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"[WARNING] Could not start cloudflared: {error}")
        return None, tunnel_ready


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
    cloudflared_process, tunnel_ready = start_cloudflared(args.port)
    tunnel_ready.wait(timeout=30)
    server = Server(
        target="main_app:app",
        address="0.0.0.0",
        port=args.port,
        interface=Interfaces.ASGI,
        workers=1,
        reload=False,
    )

    server.serve()
