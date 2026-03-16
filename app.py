"""Flask app for NSE Market Dashboard."""

from __future__ import annotations

from flask import Flask, jsonify, render_template

from utils.nse_fetch import NSEFetcher

app = Flask(__name__)
fetcher = NSEFetcher()


@app.get("/")
def index():
    """Render dashboard page."""
    return render_template("index.html")


@app.get("/api/indices")
def get_indices():
    """API endpoint consumed by frontend every 30 seconds."""
    try:
        payload = fetcher.get_indices_payload()
        return jsonify(payload)
    except Exception as exc:  # noqa: BLE001 - return readable API errors to UI.
        return (
            jsonify(
                {
                    "error": "Unable to fetch live NSE data",
                    "details": str(exc),
                }
            ),
            503,
        )


if __name__ == "__main__":
    # Runs locally on http://localhost:5000
    app.run(host="0.0.0.0", port=5000, debug=True)
