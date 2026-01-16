"""
Web Server Runner Script.
Web服务器运行脚本

Start the FastAPI web server for VNPy AI Trader.
启动VNPy AI Trader的FastAPI Web服务器。

Usage:
    python run_web_server.py
    python run_web_server.py --host 0.0.0.0 --port 8080
    python run_web_server.py --reload  # Development mode with auto-reload
"""

import argparse
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run VNPy AI Trader Web Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with default settings (localhost:8000)
  python run_web_server.py

  # Custom host and port
  python run_web_server.py --host 0.0.0.0 --port 8080

  # Development mode with auto-reload
  python run_web_server.py --reload

  # Production mode with multiple workers
  python run_web_server.py --workers 4
        """,
    )

    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Log level (default: info)",
    )

    return parser.parse_args()


def check_environment():
    """Check environment configuration."""
    print("=" * 60)
    print("VNPy AI Trader Web Server")
    print("=" * 60)

    # Check DeepSeek API key
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if api_key:
        print(f"[OK] DeepSeek API Key: ...{api_key[-8:]}")
    else:
        print("[WARN] DeepSeek API Key not set. Natural language parsing will not work.")
        print("       Set it with: set DEEPSEEK_API_KEY=your_key")

    print()


def main():
    """Main entry point."""
    args = parse_args()

    check_environment()

    print(f"Starting server on http://{args.host}:{args.port}")
    print(f"API docs available at http://{args.host}:{args.port}/docs")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)

    # Run uvicorn
    uvicorn.run(
        "src.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
