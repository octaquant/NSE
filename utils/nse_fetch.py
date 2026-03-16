"""Utilities for fetching, caching, and enriching NSE index data for the dashboard."""

from __future__ import annotations

import datetime as dt
import threading
from typing import Dict, List, Tuple

import pandas as pd
import requests
from zoneinfo import ZoneInfo

NSE_HOME_URL = "https://www.nseindia.com"
NSE_ALL_INDICES_URL = "https://www.nseindia.com/api/allIndices"
IST = ZoneInfo("Asia/Kolkata")

# A browser-like header set helps avoid NSE's anti-bot blocks.
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

# Core headline indices shown as overview cards.
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
    """Maintains a live NSE session and in-memory cache for downstream API routes."""

    def __init__(self, timeout: int = 10, refresh_interval_seconds: int = 20) -> None:
        self.timeout = timeout
        self.refresh_interval_seconds = refresh_interval_seconds
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._session_initialized = False
        self._lock = threading.Lock()
        self._cache: Dict = {
            "last_fetch_utc": None,
            "payload": {
                "last_updated": "--",
                "count": 0,
                "indices": [],
                "top_bullish": [],
                "top_bearish": [],
                "market_signal": {
                    "label": "SIDEWAYS MARKET",
                    "reason": "Waiting for first market snapshot.",
                },
                "india_vix": {
                    "last_price": 0,
                    "change": 0,
                    "percent_change": 0,
                    "zone": "neutral",
                },
            },
        }

    def _initialize_session(self) -> None:
        """Warm up session cookies by first hitting NSE home page."""
        if self._session_initialized:
            return
        self.session.get(NSE_HOME_URL, timeout=self.timeout)
        self._session_initialized = True

    def _fetch_raw_indices(self) -> List[Dict]:
        """Fetch raw index records from NSE API with a one-time reinitialize retry."""
        self._initialize_session()
        response = self.session.get(NSE_ALL_INDICES_URL, timeout=self.timeout)
        if response.status_code != 200:
            self._session_initialized = False
            self._initialize_session()
            response = self.session.get(NSE_ALL_INDICES_URL, timeout=self.timeout)

        response.raise_for_status()
        payload = response.json()
        return payload.get("data", [])

    @staticmethod
    def _to_number(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
        """Safely coerce potentially missing columns into numeric data."""
        return pd.to_numeric(frame.get(column, default), errors="coerce").fillna(default)

    def _extract_india_vix(self, frame: pd.DataFrame) -> Dict:
        """Extract India VIX snapshot and classify into dashboard color zones."""
        vix_row = frame[frame["index"] == "INDIA VIX"]
        if vix_row.empty:
            return {"last_price": 0, "change": 0, "percent_change": 0, "zone": "neutral"}

        last_price = float(vix_row["last"].iloc[0])
        change = float(vix_row["variation"].iloc[0])
        pct_change = float(vix_row["percentChange"].iloc[0])

        if last_price >= 18:
            zone = "risk-high"
        elif last_price >= 14:
            zone = "risk-medium"
        else:
            zone = "risk-low"

        return {
            "last_price": last_price,
            "change": change,
            "percent_change": pct_change,
            "zone": zone,
        }

    def _market_signal(self, frame: pd.DataFrame, india_vix: Dict) -> Dict:
        """Derive liquidity + momentum regime using breadth, volume, and volatility expansion."""
        avg_pct = frame["percent_change"].mean()
        avg_abs_pct = frame["percent_change"].abs().mean()
        avg_volume_ratio = frame["volume_expansion"].mean()
        vix_change = india_vix.get("percent_change", 0.0)

        bullish = avg_pct > 0.35 and avg_volume_ratio > 1.1 and avg_abs_pct > 0.45 and vix_change <= 1.5
        bearish = avg_pct < -0.35 and avg_volume_ratio > 1.1 and avg_abs_pct > 0.45 and vix_change >= -1.5

        if bullish:
            label = "BULLISH MOMENTUM"
        elif bearish:
            label = "BEARISH MOMENTUM"
        else:
            label = "SIDEWAYS MARKET"

        return {
            "label": label,
            "reason": (
                f"Breadth {avg_pct:.2f}%, volume expansion {avg_volume_ratio:.2f}x, "
                f"volatility expansion {avg_abs_pct:.2f}, India VIX Δ {vix_change:.2f}%"
            ),
        }

    def _build_payload(self, raw_rows: List[Dict]) -> Dict:
        """Transform NSE feed into frontend-ready records and analytical summaries.

        Data pipeline:
        1) Parse entire NSE allIndices response into DataFrame.
        2) Extract India VIX from the full universe.
        3) Filter target sector indices and normalize numeric fields.
        4) Compute volume/volatility expansion and market momentum labels.
        5) Return one compact payload for all dashboard panels.
        """
        frame = pd.DataFrame(raw_rows)
        if frame.empty:
            now_ist = dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
            return {"last_updated": now_ist, "count": 0, "indices": [], "top_bullish": [], "top_bearish": []}

        for col in ["last", "variation", "percentChange", "open", "previousClose", "high", "low", "totalTradedVolume"]:
            frame[col] = self._to_number(frame, col)

        if "high" not in frame.columns:
            frame["high"] = self._to_number(frame, "yearHigh")
        if "low" not in frame.columns:
            frame["low"] = self._to_number(frame, "yearLow")

        india_vix = self._extract_india_vix(frame)

        filtered = frame[frame["index"].isin(TARGET_INDICES)].copy()
        if filtered.empty:
            now_ist = dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
            return {"last_updated": now_ist, "count": 0, "indices": [], "top_bullish": [], "top_bearish": [], "india_vix": india_vix}

        filtered.rename(
            columns={
                "index": "index_name",
                "last": "last_price",
                "variation": "change",
                "percentChange": "percent_change",
                "previousClose": "previous_close",
                "totalTradedVolume": "volume",
            },
            inplace=True,
        )

        volume_mean = max(filtered["volume"].mean(), 1)
        filtered["volume_expansion"] = (filtered["volume"] / volume_mean).round(2)
        filtered["volatility_expansion"] = (filtered["percent_change"].abs() / max(filtered["percent_change"].abs().mean(), 0.01)).round(2)

        filtered.sort_values(by="percent_change", ascending=False, inplace=True)
        top_bullish = filtered.head(3)[["index_name", "percent_change"]].to_dict(orient="records")
        top_bearish = filtered.tail(3).sort_values(by="percent_change")[["index_name", "percent_change"]].to_dict(orient="records")

        market_signal = self._market_signal(filtered, india_vix)
        now_ist = dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

        records = filtered[
            [
                "index_name",
                "last_price",
                "change",
                "percent_change",
                "high",
                "low",
                "open",
                "previous_close",
                "volume",
                "volume_expansion",
                "volatility_expansion",
            ]
        ].fillna(0).to_dict(orient="records")

        return {
            "last_updated": now_ist,
            "count": len(records),
            "indices": records,
            "top_bullish": top_bullish,
            "top_bearish": top_bearish,
            "market_signal": market_signal,
            "india_vix": india_vix,
        }

    def refresh_if_due(self, force: bool = False) -> Dict:
        """Refresh cache only when stale (>= refresh interval) unless force is requested."""
        with self._lock:
            last_fetch = self._cache["last_fetch_utc"]
            now_utc = dt.datetime.now(dt.timezone.utc)
            if not force and last_fetch and (now_utc - last_fetch).total_seconds() < self.refresh_interval_seconds:
                return self._cache["payload"]

            raw_rows = self._fetch_raw_indices()
            self._cache["payload"] = self._build_payload(raw_rows)
            self._cache["last_fetch_utc"] = now_utc
            return self._cache["payload"]

    def get_indices_payload(self) -> Dict:
        """Return latest payload using server-side caching to avoid repeated API calls."""
        return self.refresh_if_due(force=False)
