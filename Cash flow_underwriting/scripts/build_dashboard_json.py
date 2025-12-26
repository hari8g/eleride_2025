from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


def find_latest_dir(root: Path, prefix: str) -> Path:
    if not root.exists():
        raise FileNotFoundError(f"Missing root: {root}")
    candidates = [p for p in root.iterdir() if p.is_dir() and p.name.startswith(prefix)]
    if not candidates:
        raise FileNotFoundError(f"No {prefix}* folders under: {root}")
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        # allow empty csvs with header-only / empty
        try:
            return pd.read_csv(path, nrows=0)
        except Exception:
            return pd.DataFrame()


def to_records(df: pd.DataFrame, limit: int | None = None) -> list[dict]:
    if df is None or df.empty:
        return []
    if limit is not None:
        df = df.head(limit)
    # convert NaN to None for JSON
    recs = df.where(pd.notnull(df), None).to_dict(orient="records")
    return recs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a single dashboard.json for the frontend from latest outputs.")
    parser.add_argument("--root", type=str, default=".", help="Project root")
    parser.add_argument("--features-root", type=str, default="outputs", help="Folder containing run_* feature outputs")
    parser.add_argument("--underwriting-root", type=str, default="outputs_underwriting", help="Folder containing uw_* outputs")
    parser.add_argument("--out", type=str, default="frontend/data/dashboard.json", help="Where to write dashboard JSON")
    parser.add_argument("--max-offers", type=int, default=5000, help="Max offers rows to embed")
    parser.add_argument("--max-fact-rows", type=int, default=20000, help="Max fact rider-week rows to embed")
    args = parser.parse_args()

    project_root = Path(args.root).expanduser().resolve()
    features_root = (project_root / args.features_root).resolve()
    uw_root = (project_root / args.underwriting_root).resolve()

    latest_run = find_latest_dir(features_root, "run_")
    latest_uw_lender = find_latest_dir(uw_root, "uw_salary_advance_lender_")
    latest_uw_3pl = find_latest_dir(uw_root, "uw_3pl_operator_")

    # Feature outputs
    fact = read_csv_safe(latest_run / "fact_rider_week.csv")
    dim = read_csv_safe(latest_run / "dim_rider.csv")
    rider_features = read_csv_safe(latest_run / "rider_underwriting_features.csv")

    # Underwriting outputs
    lender_offers = read_csv_safe(latest_uw_lender / "offers.csv")
    lender_portfolio = read_csv_safe(latest_uw_lender / "portfolio_summary.csv")

    threepl_offers = read_csv_safe(latest_uw_3pl / "offers.csv")
    threepl_portfolio = read_csv_safe(latest_uw_3pl / "portfolio_summary.csv")
    threepl_wc = read_csv_safe(latest_uw_3pl / "3pl_working_capital_summary.csv")

    # Keep payload bounded (still fine for your current dataset sizes)
    if not fact.empty and fact.shape[0] > args.max_fact_rows:
        fact = fact.sort_values(["year", "month", "week"]).tail(args.max_fact_rows)
    if not lender_offers.empty and lender_offers.shape[0] > args.max_offers:
        lender_offers = lender_offers.head(args.max_offers)
    if not threepl_offers.empty and threepl_offers.shape[0] > args.max_offers:
        threepl_offers = threepl_offers.head(args.max_offers)

    # Create a compact time series per rider for sparklines (week_id + net_payout)
    rider_ts: dict[str, list[dict]] = {}
    if not fact.empty and "rider_key" in fact.columns:
        cols = [c for c in ["rider_key", "week_id", "year", "month", "week", "net_payout", "delivered_orders", "attendance"] if c in fact.columns]
        f2 = fact[cols].copy()
        sort_cols = [c for c in ["year", "month", "week"] if c in f2.columns]
        if sort_cols:
            f2 = f2.sort_values(sort_cols)
        for rk, g in f2.groupby("rider_key", dropna=False):
            rk = str(rk)
            rider_ts[rk] = to_records(g.drop(columns=["rider_key"], errors="ignore"))

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "latest_feature_run_dir": str(latest_run),
        "latest_uw_lender_dir": str(latest_uw_lender),
        "latest_uw_3pl_dir": str(latest_uw_3pl),
        "portfolio": {
            "lender": to_records(lender_portfolio),
            "threepl": to_records(threepl_portfolio),
            "threepl_working_capital": to_records(threepl_wc),
        },
        "tables": {
            "lender_offers": to_records(lender_offers),
            "threepl_offers": to_records(threepl_offers),
            "rider_features": to_records(rider_features),
            "dim_rider": to_records(dim),
        },
        "series": {
            "rider_week": rider_ts,
        },
    }

    out_path = (project_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote dashboard JSON: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


