"""
Deep-Sniper AI Dashboard Standalone Launcher.
Serves the FastAPI Web Gateway and WebSocket Hub.
Enables local access, LAN access from phone/tablet, and optional remote tunnel.
"""
import argparse
import socket
import urllib.parse
import uvicorn
from loguru import logger

VERCEL_UI = "https://mult-trade-forex.vercel.app"


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


def start_ngrok_tunnel(port: int):
    """Optional ngrok public tunnel launcher."""
    try:
        import ngrok
        logger.info("[Tunnel] Attempting to establish ngrok public tunnel...")
        listener = ngrok.forward(port, authtoken_from_env=True)
        public_url = str(listener.url()).rstrip("/")
        logger.info(f"PUBLIC TUNNEL: {public_url}")
        bridge = f"{VERCEL_UI}?backend={urllib.parse.quote(public_url, safe='')}"
        print("=" * 65)
        print("Vercel bridge (open this once — UI remembers tunnel):")
        print(f"  {bridge}")
        print("Or open the tunnel URL directly (UI+API same origin):")
        print(f"  {public_url}")
        print("=" * 65)
        return listener
    except Exception as e:
        logger.warning(
            f"[Tunnel] Could not auto-start ngrok ({e}).\n"
            f"  Manual: ngrok http {port}\n"
            f"  Then open: {VERCEL_UI}?backend=https://YOUR-NGROK-URL"
        )
        return None


def main():
    parser = argparse.ArgumentParser(description="Deep-Sniper AI Dashboard Server")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host (default 0.0.0.0 for LAN access)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default 8000)")
    parser.add_argument("--tunnel", action="store_true", help="Launch public ngrok tunnel for remote mobile access")
    args = parser.parse_args()

    local_ip = get_local_ip()

    print("=" * 65)
    print("DEEP-SNIPER AI - QUANT WEB DASHBOARD")
    print("=" * 65)
    print(f"Local Machine:      http://localhost:{args.port}")
    print(f"Phone on same Wi-Fi: http://{local_ip}:{args.port}")
    print(f"Vercel UI (needs tunnel): {VERCEL_UI}")
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
