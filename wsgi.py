"""WSGI entrypoint for Render and production deployment.

TraceLedger Forensic Intelligence Suite.
"""
from traceledger.web.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)

