"""
Deep-Sniper AI Dashboard Standalone Launcher.
Serves the FastAPI Web Gateway and WebSocket Hub.
Enables local access, LAN access from phone/tablet, and optional remote tunnel.
"""
import argparse
import socket
import sys
import uvicorn
from loguru import logger

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
        # Note: ngrok.forward may require NGROK_AUTHTOKEN environment variable
        listener = ngrok.forward(port, authtoken_from_env=True)
        logger.info(f"🌐 PUBLIC REMOTE URL (Accessible from mobile anywhere): {listener.url()}")
        return listener
    except Exception as e:
        logger.warning(
            f"[Tunnel] Could not auto-start ngrok ({e}).\n"
            f"💡 To create a remote tunnel manually while at class, run in another terminal:\n"
            f"   ngrok http {port}  OR  npx localtunnel --port {port}"
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
    print("🚀 DEEP-SNIPER AI - QUANT WEB DASHBOARD")
    print("=" * 65)
    print(f"💻 Local Machine:      http://localhost:{args.port}")
    print(f"📱 Phone on same Wi-Fi: http://{local_ip}:{args.port}")
    print("⚡ Real-time Telemetry: RTX 4050 VRAM, Ryzen 7 CPU, MT5 & $50 Shield")
    print("=" * 65)

    if args.tunnel:
        start_ngrok_tunnel(args.port)

    # Run uvicorn server
    uvicorn.run(
        "dashboard.app:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
