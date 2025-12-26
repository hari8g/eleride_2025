import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.core.config import settings


@dataclass
class CacheEntry:
    mtime: float
    df: pd.DataFrame


# Global cache for Excel files
_excel_cache: dict[str, CacheEntry] = {}


def get_data_dir() -> Path:
    """Get the cashflow data directory path."""
    # Try environment variable first, then default to a mounted path
    data_dir = os.getenv("CASHFLOW_DATA_DIR", "/app/cashflow_data")
    return Path(data_dir).expanduser().resolve()


def list_xlsx_files() -> list[str]:
    """List all .xlsx files in the data directory."""
    data_dir = get_data_dir()
    if not data_dir.exists():
        return []
    files = sorted([p.name for p in data_dir.glob("*.xlsx") if not p.name.startswith("~$")])
    return files


def normalize_id(x: object) -> str:
    """Normalize ids like 756045.0 -> '756045'."""
    if x is None:
        return ""
    try:
        if isinstance(x, float) and pd.isna(x):
            return ""
    except Exception:
        pass
    s = str(x).strip()
    if s.endswith(".0"):
        s2 = s[:-2]
        if s2.isdigit():
            return s2
    # if it's a float string like '756045.0'
    try:
        fv = float(s)
        if fv.is_integer():
            return str(int(fv))
    except Exception:
        pass
    return s


def load_excel(filename: str) -> pd.DataFrame:
    """Load an Excel file with caching."""
    data_dir = get_data_dir()
    # allow only file basenames inside data_dir
    safe = Path(filename).name
    path = data_dir / safe
    if not path.exists():
        raise FileNotFoundError(f"File not found: {safe}")

    mtime = path.stat().st_mtime
    ce = _excel_cache.get(safe)
    if ce and ce.mtime == mtime:
        return ce.df

    df = pd.read_excel(path, sheet_name=0, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    _excel_cache[safe] = CacheEntry(mtime=mtime, df=df)
    return df


def infer_week_label(df: pd.DataFrame) -> str:
    """Infer week label from dataframe columns."""
    if all(c in df.columns for c in ["year", "month", "week"]):
        y = int(df["year"].dropna().iloc[0]) if not df["year"].dropna().empty else None
        m = int(df["month"].dropna().iloc[0]) if not df["month"].dropna().empty else None
        w = int(df["week"].dropna().iloc[0]) if not df["week"].dropna().empty else None
        if y and m and w:
            return f"{y}-{m:02d}-W{w}"
    return ""


def build_payslip_row(df: pd.DataFrame, cee_id: str) -> dict:
    """Build payslip data for a rider from Excel data."""
    if "cee_id" not in df.columns:
        raise ValueError("Sheet missing cee_id column")
    target = normalize_id(cee_id)
    sub = df[df["cee_id"].map(normalize_id) == target].copy()
    if sub.empty:
        raise FileNotFoundError(f"Rider cee_id not found in sheet: {cee_id}")

    # If multiple rows (e.g. multiple stores), aggregate numeric and keep representative text fields.
    numeric_cols = [c for c in sub.columns if pd.api.types.is_numeric_dtype(sub[c])]
    text_cols = [c for c in sub.columns if c not in numeric_cols]

    agg = {}
    for c in numeric_cols:
        agg[c] = float(pd.to_numeric(sub[c], errors="coerce").fillna(0).sum())
    for c in text_cols:
        # take first non-null
        s = sub[c].dropna()
        agg[c] = s.iloc[0] if not s.empty else None

    # Normalize key sections
    key = {
        "cee_id": normalize_id(agg.get("cee_id")),
        "cee_name": agg.get("cee_name"),
        "pan": agg.get("pan"),
        "city": agg.get("city"),
        "store": agg.get("store"),
        "delivery_mode": agg.get("delivery_mode"),
        "lmd_provider": agg.get("lmd_provider"),
        "rate_card_id": agg.get("rate_card_id"),
        "settlement_frequency": agg.get("settlement_frequency"),
        "period": infer_week_label(df),
    }

    ops = {
        "delivered_orders": agg.get("delivered_orders", 0.0),
        "cancelled_orders": agg.get("cancelled_orders", 0.0),
        "weekday_orders": agg.get("weekday_orders", 0.0),
        "weekend_orders": agg.get("weekend_orders", 0.0),
        "attendance": agg.get("attendance", 0.0),
        "distance": agg.get("distance", 0.0),
    }

    pay = {
        "base_pay": agg.get("base_pay", 0.0),
        "incentive_total": agg.get("incentive_total", 0.0),
        "arrears_amount": agg.get("arrears_amount", 0.0),
        "deductions_amount": agg.get("deductions_amount", 0.0),
        "management_fee": agg.get("management_fee", 0.0),
        "gst": agg.get("gst", 0.0),
        "final_with_gst": agg.get("final_with_gst", 0.0),
        "final_with_gst_minus_settlement": agg.get("final_with_gst_minus_settlement", 0.0),
    }

    # Useful derived totals
    gross = float(pay["base_pay"] + pay["incentive_total"] + pay.get("arrears_amount", 0.0))
    net = float(pay.get("final_with_gst_minus_settlement", pay.get("final_with_gst", 0.0)))
    pay["gross_earnings_est"] = gross
    pay["net_payout"] = net

    return {"identity": key, "ops": ops, "pay": pay}


def get_riders_from_file(filename: str) -> list[dict]:
    """Get list of riders from an Excel file."""
    df = load_excel(filename)
    if "cee_id" not in df.columns:
        raise ValueError("Sheet missing cee_id")
    
    cols = [c for c in ["cee_id", "cee_name", "pan", "city", "store"] if c in df.columns]
    riders = df[cols].copy()
    riders["cee_id"] = riders["cee_id"].map(normalize_id)
    riders = riders.drop_duplicates(subset=["cee_id"]).sort_values("cee_id")
    return riders.where(pd.notnull(riders), None).to_dict(orient="records")

