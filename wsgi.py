"""
WSGI entry point.
Usage:  gunicorn wsgi:app
        python wsgi.py
"""

from app import create_app

app = create_app()


def main():
    import os
    import sys

    use_reloader = os.environ.get("USE_RELOADER", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if use_reloader and not os.path.exists(sys.executable):
        use_reloader = False

    host = os.environ.get("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_RUN_PORT", "5000"))
    app.run(debug=True, host=host, port=port, use_reloader=use_reloader)


if __name__ == "__main__":
    main()
