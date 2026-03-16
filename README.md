# NSE Market Dashboard

A professional, web-based trading terminal style dashboard for major NSE indices using a **Flask backend** and **Plotly-powered frontend**.

## Features

- Live data from NSE `allIndices` endpoint.
- Cookie/session initialization against `https://www.nseindia.com` to avoid blocked requests.
- Auto-refresh every 30 seconds.
- Card layout for major indices.
- Interactive Plotly visualizations:
  - Index Performance Bar Chart (% change)
  - Market Heatmap (bullish vs bearish)
- Full table view with key fields:
  - Index Name
  - Last Price
  - Change
  - % Change
  - High
  - Low
  - Open
  - Previous Close
- Color coding (green/red) for market trend.
- Last updated status timer.

## Project Structure

```text
nse-dashboard/
│
├── app.py
├── requirements.txt
├── Procfile
├── templates/
│   └── index.html
├── static/
│   └── styles.css
├── utils/
│   └── nse_fetch.py
└── README.md
```

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open: `http://localhost:5000`

## How data fetching works

1. `requests.Session()` is created once and reused.
2. It first calls `https://www.nseindia.com` to establish cookies.
3. Then it requests `https://www.nseindia.com/api/allIndices`.
4. Data is parsed into a pandas DataFrame and normalized into frontend JSON.
5. Frontend requests `/api/indices` every 30 seconds.

## Deployment

### Render

- Create a new **Web Service** from this repo.
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`

### Railway

- Deploy this repo.
- Railway will use `Procfile` automatically.
- Ensure start command: `gunicorn app:app --bind 0.0.0.0:$PORT`

### Streamlit Cloud

Streamlit Cloud can run custom commands in advanced settings. Use:

- Install command: `pip install -r requirements.txt`
- Run command: `gunicorn app:app --bind 0.0.0.0:$PORT`

> If your Streamlit workspace enforces `streamlit run`, deploy this project on Render/Railway instead.
