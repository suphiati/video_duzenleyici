"""Desktop entry point — starts the local server and opens the browser.

This is the PyInstaller entry point (see build_exe.ps1). Importing ``app.main``
at module scope ensures PyInstaller bundles the whole FastAPI app graph.

The port stays 8000 because the YouTube OAuth redirect is hard-coded to it
(youtube_service.py).
"""

import sys
import threading
import time
import webbrowser

import uvicorn

from app.main import app  # noqa: F401  (pulls the full app graph into the bundle)

if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def _open_browser_when_ready() -> None:
    # Give uvicorn a moment to bind the socket before opening the tab.
    time.sleep(1.5)
    try:
        webbrowser.open(URL)
    except Exception:
        pass


def main() -> None:
    print("=" * 52)
    print("  Video Duzenleyici calisiyor")
    print(f"  Tarayici: {URL}")
    print("  Kapatmak icin bu pencereyi kapatin (veya Ctrl+C).")
    print("=" * 52)
    threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
