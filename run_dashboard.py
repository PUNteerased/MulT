"""
Deep-Sniper AI Dashboard Standalone Launcher.
Serves the FastAPI Web Gateway and WebSocket Hub.
Enables local access, LAN access from phone/tablet, and optional remote tunnel.
"""
import argparse
import os
import socket
import urllib.parse
import uvicorn
from loguru import logger

VERCEL_UI = "https://mult-trade-forex.vercel.app"
# Free ngrok static Dev Domain (never changes across restarts)
NGROK_DOMAIN = os.environ.get(
    "NGROK_DOMAIN",
    "beula-nonintersecting-frigidly.ngrok-free.dev",
)
STATIC_TUNNEL_URL = f"https://{NGROK_DOMAIN}"


def load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE pairs into os.environ (does not override existing)."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


def get_local_ip() -> str:
    """Detect LAN IP address of this laptop."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def print_tunnel_urls(public_url: str) -> None:
    bridge = f"{VERCEL_UI}?backend={urllib.parse.quote(public_url, safe='')}"
    print("=" * 65)
    print("Static tunnel URL (same every time):")
    print(f"  {public_url}")
    print("Vercel bridge (open once — UI + localStorage remember it):")
    print(f"  {bridge}")
    print("=" * 65)


def start_ngrok_tunnel(port: int):
    """Optional ngrok public tunnel on the account Dev Domain."""
    try:
        import ngrok
        logger.info(f"[Tunnel] Binding ngrok Dev Domain: {NGROK_DOMAIN}")
        listener = ngrok.forward(
            port,
            authtoken_from_env=True,
            domain=NGROK_DOMAIN,
        )
        public_url = str(listener.url()).rstrip("/") or STATIC_TUNNEL_URL
        logger.info(f"PUBLIC TUNNEL: {public_url}")
        print_tunnel_urls(public_url)
        return listener
    except Exception as e:
        logger.warning(
            f"[Tunnel] Could not auto-start ngrok ({e}).\n"
            f"  Manual (static URL):\n"
            f"    ngrok http {port} --url {STATIC_TUNNEL_URL}\n"
            f"  Then open once:\n"
            f"    {VERCEL_UI}?backend={STATIC_TUNNEL_URL}"
        )
        return None


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Deep-Sniper AI Dashboard Server")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host (default 0.0.0.0 for LAN access)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default 8000)")
    parser.add_argument("--tunnel", action="store_true", help="Launch public ngrok tunnel for remote mobile access")
    args = parser.parse_args()

    local_ip = get_local_ip()
    auth_on = bool(os.environ.get("DASHBOARD_PASSWORD", "").strip())

    print("=" * 65)
    print("DEEP-SNIPER AI - QUANT WEB DASHBOARD")
    print("=" * 65)
    print(f"Local Machine:      http://localhost:{args.port}")
    print(f"Phone on same Wi-Fi: http://{local_ip}:{args.port}")
    print(f"Vercel UI:          {VERCEL_UI}")
    print(f"Static ngrok URL:   {STATIC_TUNNEL_URL}")
    print(f"Auth gate:          {'ON (DASHBOARD_PASSWORD set)' if auth_on else 'OFF'}")
    print("=" * 65)
    print("Remote access (after dashboard is up):")
    print(f"  ngrok http {args.port} --url {STATIC_TUNNEL_URL}")
    print("=" * 65)

    if args.tunnel:
        start_ngrok_tunnel(args.port)

    uvicorn.run(
        "dashboard.app:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
