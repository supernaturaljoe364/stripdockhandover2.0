"""Start the StripDock app: http://localhost:5000"""
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.station import Station  # noqa: E402
from app.web import create_app  # noqa: E402


def main():
    st = Station()
    app = create_app(st)
    host, port = st.cfg["web"]["host"], int(st.cfg["web"]["port"])
    print(f"StripDock running at http://localhost:{port}  (Ctrl+C to stop)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(f"http://localhost:{port}")
    try:
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    finally:
        st.stop()


if __name__ == "__main__":
    main()
