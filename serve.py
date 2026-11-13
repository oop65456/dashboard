"""Phase 5: show the dashboard on this PC at http://127.0.0.1:8000

    python serve.py            # serve public/ and open the browser
    python serve.py --no-open  # serve only

Serves the files in public/ and nothing else. Bound to 127.0.0.1, so only this PC can see it
(the phone version comes in Phase 7 via GitHub Pages). Port 8000, so it never clashes with
your old dashboard on 8765. Read-only: there is no way to place an order through this server.
"""
import functools
import http.server
import sys
import webbrowser
from pathlib import Path

HOST, PORT = "127.0.0.1", 8000
PUBLIC = Path(__file__).resolve().parent / "public"


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Always fetch fresh signals and charts instead of a cached copy.
        if self.path.split("?")[0].endswith(".json"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):     # keep the window quiet
        pass


def main():
    handler = functools.partial(Handler, directory=str(PUBLIC))
    try:
        server = http.server.ThreadingHTTPServer((HOST, PORT), handler)
    except OSError:
        print(f"Port {PORT} is busy: the dashboard is probably already running. Opening it.")
        webbrowser.open(f"http://{HOST}:{PORT}/")
        return 0
    print(f"Dashboard: http://{HOST}:{PORT}/   (close this window to stop it)")
    if "--no-open" not in sys.argv:
        webbrowser.open(f"http://{HOST}:{PORT}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
