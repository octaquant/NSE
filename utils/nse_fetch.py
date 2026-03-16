"""Utilities for fetching and normalizing NSE index data."""

from __future__ import annotations

import datetime as dt
from typing import Dict, List, Tuple

import pandas as pd
import requests

NSE_HOME_URL = "https://www.nseindia.com"
NSE_ALL_INDICES_URL = "https://www.nseindia.com/api/allIndices"

# A browser-like header set helps avoid NSE's anti-bot blocks.
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

# Important indices requested by the user.
TARGET_INDICES = [
    "NIFTY 50",
    "NIFTY BANK",
    "NIFTY FINANCIAL SERVICES",
    "NIFTY MIDCAP 100",
    "NIFTY NEXT 50",
    "NIFTY IT",
    "NIFTY FMCG",
    "NIFTY AUTO",
    "NIFTY METAL",
    "NIFTY PHARMA",
    "NIFTY REALTY",
    "NIFTY ENERGY",
]


class NSEFetcher:
    """Maintains a session with NSE and returns cleaned index data."""

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._session_initialized = False

    def _initialize_session(self) -> None:
        """Warm up session cookies by first hitting NSE home page."""
        if self._session_initialized:
            return

        self.session.get(NSE_HOME_URL, timeout=self.timeout)
        self._session_initialized = True

    def _fetch_raw_indices(self) -> List[Dict]:
        """Fetch raw index records from NSE API with retry-friendly reinit."""
        self._initialize_session()

        response = self.session.get(NSE_ALL_INDICES_URL, timeout=self.timeout)
        # If session expires or is blocked, retry once after reinitializing cookies.
        if response.status_code != 200:
            self._session_initialized = False
            self._initialize_session()
            response = self.session.get(NSE_ALL_INDICES_URL, timeout=self.timeout)

        response.raise_for_status()
        payload = response.json()
        return payload.get("data", [])

    def get_indices_dataframe(self) -> Tuple[pd.DataFrame, str]:
        """Return cleaned DataFrame for selected indices and update timestamp."""
        raw_rows = self._fetch_raw_indices()
        frame = pd.DataFrame(raw_rows)

        if frame.empty:
            return pd.DataFrame(), dt.datetime.now(dt.timezone.utc).isoformat()

        filtered = frame[frame["index"].isin(TARGET_INDICES)].copy()

        # NSE sometimes uses different field names for high/low depending on feed type.
        if "high" not in filtered.columns:
            filtered["high"] = filtered.get("yearHigh", 0)
        if "low" not in filtered.columns:
            filtered["low"] = filtered.get("yearLow", 0)

        # Ensure numeric types are parsed correctly for charting and formatting.
        numeric_cols = [
            "last",
            "variation",
            "percentChange",
            "high",
            "low",
            "open",
            "previousClose",
        ]

        for col in numeric_cols:
            filtered[col] = pd.to_numeric(filtered[col], errors="coerce")

        # Friendly display labels used by the frontend.
        filtered.rename(
            columns={
                "index": "index_name",
                "last": "last_price",
                "variation": "change",
                "percentChange": "percent_change",
                "open": "open",
                "previousClose": "previous_close",
            },
            inplace=True,
        )

        filtered.sort_values(by="percent_change", ascending=False, inplace=True)

        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
        return filtered, timestamp

    def get_indices_payload(self) -> Dict:
        """Return frontend-ready JSON payload."""
        frame, timestamp = self.get_indices_dataframe()

        records = []
        if not frame.empty:
            records = frame[
                [
                    "index_name",
                    "last_price",
                    "change",
                    "percent_change",
                    "high",
                    "low",
                    "open",
                    "previous_close",
                ]
            ].fillna(0).to_dict(orient="records")

        return {
            "last_updated": timestamp,
            "count": len(records),
            "indices": records,
        }
