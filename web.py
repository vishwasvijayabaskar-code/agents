"""Convenience launcher for the web UI. Runs on http://localhost:8000"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="agents web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    args = parser.parse_args()

    print(f"Agents web UI → http://{args.host}:{args.port}")
    uvicorn.run(
        "web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
