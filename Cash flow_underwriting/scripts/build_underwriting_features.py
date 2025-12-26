from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from rapidfuzz import fuzz


MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


DEFAULT_NET_PAYOUT_CANDIDATES = [
    "final_with_gst_minus_settlement",
    "final_with_gst",
    "total_with_management_fee",
    "total_with_arrears_and_deductions",
    "total_with_arrears",
    "base_pay",
]


def _safe_lower(x: object) -> str:
    return "" if x is None else str(x).strip().lower()


def _clean_name(name: object) -> str:
    s = _safe_lower(name)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _as_int(x: object) -> int | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    try:
        return int(x)
    except Exception:
        return None


def _parse_week_from_filename(path: Path) -> tuple[int | None, int | None, int | None]:
    """
    Best-effort parser for year/month/week from filename like:
      'ELERIDE IBBN Payout Sep 25 WEEK 4.xlsx'
      'ELERIDE IBBN Payout Dec 25 WEEK 1 (1).xlsx'
    Returns (year, month, week) or (None, None, None) if not found.
    """
    name = path.stem
    s = _safe_lower(name)

    # Find month token
    month = None
    for k, v in MONTH_MAP.items():
        if re.search(rf"\b{re.escape(k)}\b", s):
            month = v
            break

    # Find 'WEEK <n>'
    m_week = re.search(r"\bweek\s*(\d+)\b", s)
    week = int(m_week.group(1)) if m_week else None

    # Find a 2-digit or 4-digit year near the month token; prefer 4-digit if present
    m_year4 = re.search(r"\b(20\d{2})\b", s)
    if m_year4:
        year = int(m_year4.group(1))
    else:
        m_year2 = re.search(r"\b(\d{2})\b", s)
        year = 2000 + int(m_year2.group(1)) if m_year2 else None

    return year, month, week


def _week_id(year: int, month: int, week: int) -> str:
    return f"{year}-{month:02d}-W{week}"


def _mode(series: pd.Series) -> object:
    s = series.dropna()
    if s.empty:
        return np.nan
    vc = s.value_counts()
    return vc.index[0] if not vc.empty else np.nan


def _ensure_columns_lower(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _pick_net_payout_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = set(df.columns)
    for c in candidates:
        if c in cols:
            return c
    return None


def _numeric_columns(df: pd.DataFrame, exclude: set[str]) -> list[str]:
    num_cols = [c for c in df.columns if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]
    return num_cols


def _compute_streak_stats(active_weeks: Iterable[int]) -> tuple[int, int, int]:
    """
    Given iterable of active week_seq integers, compute:
      (active_week_count, longest_streak, current_streak_at_end)
    """
    weeks = sorted(set(int(w) for w in active_weeks))
    if not weeks:
        return 0, 0, 0
    longest = 1
    cur = 1
    for i in range(1, len(weeks)):
        if weeks[i] == weeks[i - 1] + 1:
            cur += 1
        else:
            longest = max(longest, cur)
            cur = 1
    longest = max(longest, cur)
    # current streak at end means streak ending at most recent observed active week
    current = cur
    return len(weeks), longest, current


@dataclass(frozen=True)
class OutputPaths:
    out_dir: Path
    fact_rider_week: Path
    rider_features: Path
    dim_rider: Path
    qa_identity_conflicts: Path
    qa_fuzzy_identity_links: Path
    ingestion_file_report: Path


def build_outputs(out_root: Path) -> OutputPaths:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_root / f"run_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    return OutputPaths(
        out_dir=out_dir,
        fact_rider_week=out_dir / "fact_rider_week.csv",
        rider_features=out_dir / "rider_underwriting_features.csv",
        dim_rider=out_dir / "dim_rider.csv",
        qa_identity_conflicts=out_dir / "qa_identity_conflicts.csv",
        qa_fuzzy_identity_links=out_dir / "qa_fuzzy_identity_links.csv",
        ingestion_file_report=out_dir / "ingestion_file_report.csv",
    )


def ingest_all_weeks(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
      - raw concatenated dataframe with added 'source_file'
      - ingestion file report dataframe
    """
    files = sorted([p for p in data_dir.glob("*.xlsx") if not p.name.startswith("~$")])
    if not files:
        raise FileNotFoundError(f"No .xlsx files found in: {data_dir}")

    frames: list[pd.DataFrame] = []
    reports: list[dict] = []
    for f in files:
        df = pd.read_excel(f, sheet_name=0, engine="openpyxl")
        df = _ensure_columns_lower(df)
        df["source_file"] = f.name

        # best-effort backfill year/month/week from filename if missing
        yr_fn, mo_fn, wk_fn = _parse_week_from_filename(f)
        for col, val in [("year", yr_fn), ("month", mo_fn), ("week", wk_fn)]:
            if col not in df.columns:
                df[col] = val
            else:
                if val is not None:
                    df[col] = df[col].fillna(val)

        frames.append(df)
        reports.append(
            {
                "source_file": f.name,
                "rows": int(df.shape[0]),
                "cols": int(df.shape[1]),
                "has_cee_id": int("cee_id" in df.columns),
                "has_cee_name": int("cee_name" in df.columns),
                "has_pan": int("pan" in df.columns),
                "has_delivered_orders": int("delivered_orders" in df.columns),
                "has_attendance": int("attendance" in df.columns),
                "has_net_payout": int("final_with_gst_minus_settlement" in df.columns),
            }
        )

    raw = pd.concat(frames, ignore_index=True)
    report_df = pd.DataFrame(reports).sort_values(["source_file"])
    return raw, report_df


def build_fact_rider_week(raw: pd.DataFrame, net_payout_candidates: list[str]) -> pd.DataFrame:
    df = raw.copy()

    # Identity key (prefer cee_id, then PAN, then cleaned name+city as last resort)
    if "cee_id" in df.columns:
        df["rider_id"] = df["cee_id"].astype("Int64").astype(str)
        df.loc[df["cee_id"].isna(), "rider_id"] = np.nan
    else:
        df["rider_id"] = np.nan

    df["pan_norm"] = df["pan"].astype(str).where(df.get("pan").notna(), np.nan) if "pan" in df.columns else np.nan
    df.loc[df["pan_norm"].astype(str).str.lower().isin(["none", "nan"]), "pan_norm"] = np.nan

    df["name_norm"] = df["cee_name"].map(_clean_name) if "cee_name" in df.columns else np.nan
    df["city_norm"] = df["city"].map(_safe_lower) if "city" in df.columns else np.nan

    df["rider_key"] = np.where(
        df["rider_id"].notna(),
        "cee_id:" + df["rider_id"].astype(str),
        np.where(
            df["pan_norm"].notna(),
            "pan:" + df["pan_norm"].astype(str),
            "name_city:" + df["name_norm"].astype(str) + "|" + df["city_norm"].astype(str),
        ),
    )

    # Required time keys
    for col in ["year", "month", "week"]:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' after ingestion.")
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
    df["week"] = pd.to_numeric(df["week"], errors="coerce").astype("Int64")

    df = df.dropna(subset=["year", "month", "week"]).copy()
    df["week_id"] = df.apply(lambda r: _week_id(int(r["year"]), int(r["month"]), int(r["week"])), axis=1)

    # Choose a net payout column and create a normalized net payout field
    net_col = _pick_net_payout_column(df, net_payout_candidates)
    if net_col is None:
        raise ValueError(
            "Could not find a net payout column. "
            f"Tried candidates: {net_payout_candidates}. "
            f"Available columns: {sorted(df.columns)[:30]}..."
        )
    df["net_payout"] = pd.to_numeric(df[net_col], errors="coerce").fillna(0.0)
    df["net_payout_source_col"] = net_col

    # Aggregate multiple rows per rider-week (e.g., multiple stores)
    id_cols = {
        "rider_key",
        "week_id",
        "year",
        "month",
        "week",
    }
    prefer_take_mode = [
        "rider_id",
        "cee_id",
        "cee_name",
        "pan",
        "city",
        "lmd_provider",
        "delivery_mode",
        "cee_employment_category",
        "cee_category",
        "settlement_frequency",
        "rate_card_id",
    ]
    prefer_take_mode = [c for c in prefer_take_mode if c in df.columns]

    numeric_exclude = set(prefer_take_mode) | {"source_file", "week_id", "net_payout_source_col"} | id_cols | {
        "name_norm",
        "city_norm",
        "pan_norm",
        "rider_id",
    }
    num_cols = _numeric_columns(df, exclude=numeric_exclude)

    agg: dict[str, object] = {c: "sum" for c in num_cols}
    for c in prefer_take_mode:
        agg[c] = _mode
    agg["source_file_count"] = ("source_file", lambda s: s.nunique())
    agg["source_files"] = ("source_file", lambda s: "|".join(sorted(set(map(str, s.dropna().tolist())))))
    agg["net_payout_source_col"] = ("net_payout_source_col", _mode)

    fact = (
        df.groupby(["rider_key", "week_id", "year", "month", "week"], dropna=False)
        .agg(**{k: v for k, v in agg.items() if isinstance(v, tuple)})
    )
    # pandas named aggregation requires special form; build it explicitly
    named_agg = {}
    for k, v in agg.items():
        if isinstance(v, tuple):
            named_agg[k] = v
        else:
            named_agg[k] = (k, v)

    fact = df.groupby(["rider_key", "week_id", "year", "month", "week"], dropna=False).agg(**named_agg).reset_index()

    # Work/active flag
    delivered = pd.to_numeric(fact["delivered_orders"], errors="coerce").fillna(0.0) if "delivered_orders" in fact.columns else 0.0
    attendance = pd.to_numeric(fact["attendance"], errors="coerce").fillna(0.0) if "attendance" in fact.columns else 0.0
    base_pay = pd.to_numeric(fact["base_pay"], errors="coerce").fillna(0.0) if "base_pay" in fact.columns else 0.0
    fact["is_active_week"] = ((delivered > 0) | (attendance > 0) | (base_pay > 0) | (fact["net_payout"] > 0)).astype(int)

    return fact


def build_dim_rider(fact: pd.DataFrame) -> pd.DataFrame:
    # canonical identity and QA stats
    base_cols = [c for c in ["rider_key", "cee_id", "rider_id", "cee_name", "pan", "city", "lmd_provider", "delivery_mode"] if c in fact.columns]
    dim = fact[base_cols].copy()
    dim["cee_name_norm"] = dim["cee_name"].map(_clean_name) if "cee_name" in dim.columns else np.nan

    def nunique_nonnull(s: pd.Series) -> int:
        return int(s.dropna().astype(str).nunique())

    grp = dim.groupby("rider_key", dropna=False)
    out = pd.DataFrame(
        {
            "rider_key": grp.size().index,
            "obs_weeks": grp.size().values,
            "nunique_names": grp["cee_name_norm"].apply(nunique_nonnull).values if "cee_name_norm" in dim.columns else 0,
            "nunique_pan": grp["pan"].apply(nunique_nonnull).values if "pan" in dim.columns else 0,
            "nunique_city": grp["city"].apply(nunique_nonnull).values if "city" in dim.columns else 0,
        }
    )

    # canonical: most frequent
    canon = grp.agg(
        cee_id=("cee_id", _mode) if "cee_id" in dim.columns else ("rider_key", _mode),
        rider_id=("rider_id", _mode) if "rider_id" in dim.columns else ("rider_key", _mode),
        cee_name=("cee_name", _mode) if "cee_name" in dim.columns else ("rider_key", _mode),
        pan=("pan", _mode) if "pan" in dim.columns else ("rider_key", _mode),
        city=("city", _mode) if "city" in dim.columns else ("rider_key", _mode),
        lmd_provider=("lmd_provider", _mode) if "lmd_provider" in dim.columns else ("rider_key", _mode),
        delivery_mode=("delivery_mode", _mode) if "delivery_mode" in dim.columns else ("rider_key", _mode),
    ).reset_index()

    return canon.merge(out, on="rider_key", how="left")


def build_qa_identity_conflicts(fact: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ["rider_key", "week_id", "cee_id", "cee_name", "pan", "city"] if c in fact.columns]
    tmp = fact[cols].copy()
    tmp["cee_name_norm"] = tmp["cee_name"].map(_clean_name) if "cee_name" in tmp.columns else np.nan
    grp = tmp.groupby("rider_key", dropna=False)

    def collect_unique(s: pd.Series, limit: int = 10) -> str:
        vals = sorted({str(v) for v in s.dropna().tolist() if str(v).strip() not in ["", "nan", "None"]})
        if len(vals) > limit:
            vals = vals[:limit] + [f"...(+{len(vals)-limit} more)"]
        return " | ".join(vals)

    out = pd.DataFrame(
        {
            "rider_key": grp.size().index,
            "obs_weeks": grp.size().values,
            "names": grp["cee_name_norm"].apply(collect_unique).values if "cee_name_norm" in tmp.columns else "",
            "pans": grp["pan"].apply(collect_unique).values if "pan" in tmp.columns else "",
            "cities": grp["city"].apply(collect_unique).values if "city" in tmp.columns else "",
        }
    )
    out["has_name_conflict"] = (out["names"].str.contains(r"\|")).astype(int)
    out["has_pan_conflict"] = (out["pans"].str.contains(r"\|")).astype(int)
    out["has_city_conflict"] = (out["cities"].str.contains(r"\|")).astype(int)
    return out[(out["has_name_conflict"] == 1) | (out["has_pan_conflict"] == 1) | (out["has_city_conflict"] == 1)].sort_values(
        ["has_pan_conflict", "has_name_conflict", "obs_weeks"], ascending=[False, False, False]
    )


def build_qa_fuzzy_identity_links(
    fact: pd.DataFrame,
    min_similarity: int = 95,
    max_pairs_per_city: int = 5000,
) -> pd.DataFrame:
    """
    Conservative *suggestion* report for potential identity linking when PAN is missing.
    This does NOT merge entities; it only emits candidate pairs for human review.
    """
    cols = [c for c in ["rider_key", "cee_id", "cee_name", "pan", "city", "delivery_mode", "week_id"] if c in fact.columns]
    df = fact[cols].copy()
    df["name_norm"] = df["cee_name"].map(_clean_name) if "cee_name" in df.columns else np.nan
    df["city_norm"] = df["city"].map(_safe_lower) if "city" in df.columns else np.nan

    # only consider riders with missing/blank PAN (most useful case)
    if "pan" in df.columns:
        pan_s = df["pan"].astype(str)
        df["pan_missing"] = df["pan"].isna() | pan_s.str.lower().isin(["", "nan", "none"])
        df = df[df["pan_missing"]].copy()
    else:
        df = df.copy()

    # canonical rider identity fields
    base = (
        df.groupby("rider_key", dropna=False)
        .agg(
            cee_id=("cee_id", _mode) if "cee_id" in df.columns else ("rider_key", _mode),
            cee_name=("cee_name", _mode) if "cee_name" in df.columns else ("rider_key", _mode),
            name_norm=("name_norm", _mode),
            city=("city", _mode) if "city" in df.columns else ("rider_key", _mode),
            city_norm=("city_norm", _mode),
            delivery_mode=("delivery_mode", _mode) if "delivery_mode" in df.columns else ("rider_key", _mode),
            weeks=("week_id", lambda s: sorted(set(map(str, s.dropna().tolist())))),
        )
        .reset_index()
    )

    out_rows: list[dict] = []
    for (city_norm, delivery_mode), g in base.groupby(["city_norm", "delivery_mode"], dropna=False):
        g = g.dropna(subset=["name_norm"]).copy()
        if g.shape[0] < 2:
            continue

        rider_keys = g["rider_key"].tolist()
        names = g["name_norm"].tolist()
        weeks_list = g["weeks"].tolist()

        pair_count = 0
        for i in range(len(rider_keys)):
            for j in range(i + 1, len(rider_keys)):
                if pair_count >= max_pairs_per_city:
                    break
                sim = int(fuzz.token_set_ratio(names[i], names[j]))
                if sim < min_similarity:
                    continue
                weeks_i = set(weeks_list[i])
                weeks_j = set(weeks_list[j])
                overlap = len(weeks_i & weeks_j)
                out_rows.append(
                    {
                        "city_norm": city_norm,
                        "delivery_mode": delivery_mode,
                        "rider_key_a": rider_keys[i],
                        "rider_key_b": rider_keys[j],
                        "name_a": names[i],
                        "name_b": names[j],
                        "similarity": sim,
                        "week_overlap_count": overlap,
                    }
                )
                pair_count += 1

    expected_cols = [
        "city_norm",
        "delivery_mode",
        "rider_key_a",
        "rider_key_b",
        "name_a",
        "name_b",
        "similarity",
        "week_overlap_count",
    ]
    out = pd.DataFrame(out_rows, columns=expected_cols)
    if out.empty:
        return out
    return out.sort_values(["similarity", "week_overlap_count"], ascending=[False, False]).reset_index(drop=True)


def build_rider_features(fact: pd.DataFrame) -> pd.DataFrame:
    # build week sequence index (global, across all riders) so streaks span month boundaries
    uniq_weeks = (
        fact[["year", "month", "week", "week_id"]]
        .drop_duplicates()
        .sort_values(["year", "month", "week"])
        .reset_index(drop=True)
    )
    uniq_weeks["week_seq"] = np.arange(len(uniq_weeks), dtype=int)
    fact2 = fact.merge(uniq_weeks[["week_id", "week_seq"]], on="week_id", how="left")

    grp = fact2.groupby("rider_key", dropna=False)

    def series_stats(x: pd.Series) -> dict[str, float]:
        x = pd.to_numeric(x, errors="coerce").dropna()
        x = x[x != 0]
        if x.empty:
            return {
                "mean": 0.0,
                "std": 0.0,
                "cv": 0.0,
                "median": 0.0,
                "p10": 0.0,
                "p90": 0.0,
                "min": 0.0,
                "max": 0.0,
            }
        mean = float(x.mean())
        std = float(x.std(ddof=0))
        cv = float(std / mean) if mean != 0 else 0.0
        return {
            "mean": mean,
            "std": std,
            "cv": cv,
            "median": float(x.median()),
            "p10": float(x.quantile(0.10)),
            "p90": float(x.quantile(0.90)),
            "min": float(x.min()),
            "max": float(x.max()),
        }

    rows: list[dict] = []
    for rider_key, g in grp:
        g = g.sort_values("week_seq").copy()
        active_mask = g["is_active_week"] == 1
        active_seqs = g.loc[active_mask, "week_seq"].astype(int).tolist()

        active_week_count, longest_streak, current_streak = _compute_streak_stats(active_seqs)

        # gaps
        if active_seqs:
            gaps = [b - a - 1 for a, b in zip(active_seqs[:-1], active_seqs[1:]) if b > a + 1]
            gap_count = int(sum(1 for gg in gaps if gg > 0))
            max_gap = int(max(gaps)) if gaps else 0
            weeks_since_last_active = int(g["week_seq"].max() - max(active_seqs))
        else:
            gap_count = 0
            max_gap = 0
            weeks_since_last_active = int(g["week_seq"].max()) if len(g) else 0

        # payout series on active weeks only
        payout_active = g.loc[active_mask, "net_payout"]
        payout_stats = series_stats(payout_active)

        # recent windows
        last4 = g.tail(4)
        last4_active = last4[last4["is_active_week"] == 1]
        last4_payout_mean = float(pd.to_numeric(last4_active["net_payout"], errors="coerce").mean()) if not last4_active.empty else 0.0
        last4_active_weeks = int(last4_active.shape[0])

        # base vs incentive
        base = pd.to_numeric(g.get("base_pay", 0.0), errors="coerce").fillna(0.0)
        inc = pd.to_numeric(g.get("incentive_total", 0.0), errors="coerce").fillna(0.0)
        total_comp = base + inc
        incentive_share = float((inc.sum() / total_comp.sum()) if total_comp.sum() != 0 else 0.0)

        # ops metrics (sums)
        delivered = float(pd.to_numeric(g.get("delivered_orders", 0.0), errors="coerce").fillna(0.0).sum())
        cancelled = float(pd.to_numeric(g.get("cancelled_orders", 0.0), errors="coerce").fillna(0.0).sum())
        weekday_orders = float(pd.to_numeric(g.get("weekday_orders", 0.0), errors="coerce").fillna(0.0).sum())
        weekend_orders = float(pd.to_numeric(g.get("weekend_orders", 0.0), errors="coerce").fillna(0.0).sum())
        attendance = float(pd.to_numeric(g.get("attendance", 0.0), errors="coerce").fillna(0.0).sum())

        cancel_rate = float(cancelled / (delivered + cancelled)) if (delivered + cancelled) != 0 else 0.0
        weekend_share = float(weekend_orders / (weekday_orders + weekend_orders)) if (weekday_orders + weekend_orders) != 0 else 0.0

        rows.append(
            {
                "rider_key": rider_key,
                "weeks_associated": int(g["week_id"].nunique()),
                "active_weeks_worked": int(active_week_count),
                "longest_consecutive_active_weeks": int(longest_streak),
                "current_consecutive_active_weeks": int(current_streak),
                "gap_count_between_active_weeks": int(gap_count),
                "max_gap_weeks": int(max_gap),
                "weeks_since_last_active": int(weeks_since_last_active),
                "net_payout_mean": payout_stats["mean"],
                "net_payout_std": payout_stats["std"],
                "net_payout_cv": payout_stats["cv"],
                "net_payout_median": payout_stats["median"],
                "net_payout_p10": payout_stats["p10"],
                "net_payout_p90": payout_stats["p90"],
                "net_payout_min": payout_stats["min"],
                "net_payout_max": payout_stats["max"],
                "net_payout_last4_mean": float(last4_payout_mean),
                "active_weeks_last4": int(last4_active_weeks),
                "total_net_payout_sum": float(pd.to_numeric(g["net_payout"], errors="coerce").fillna(0.0).sum()),
                "base_pay_sum": float(base.sum()),
                "incentive_total_sum": float(inc.sum()),
                "incentive_share": float(incentive_share),
                "delivered_orders_sum": delivered,
                "cancelled_orders_sum": cancelled,
                "cancel_rate": cancel_rate,
                "weekday_orders_sum": weekday_orders,
                "weekend_orders_sum": weekend_orders,
                "weekend_share": weekend_share,
                "attendance_days_sum": attendance,
            }
        )

    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build underwriting features from weekly payout Excel files.")
    parser.add_argument("--data-dir", type=str, default="Data", help="Directory containing weekly .xlsx payout files")
    parser.add_argument("--out-dir", type=str, default="outputs", help="Output directory (a timestamped subfolder is created)")
    parser.add_argument(
        "--net-payout-col",
        type=str,
        default="",
        help="Optional explicit net payout column to use (overrides automatic selection).",
    )
    parser.add_argument(
        "--fuzzy-linking-report",
        action="store_true",
        help="If set, emit qa_fuzzy_identity_links.csv with high-similarity name pairs (PAN-missing cases) for review.",
    )
    parser.add_argument(
        "--fuzzy-min-similarity",
        type=int,
        default=95,
        help="Minimum similarity (0-100) for fuzzy identity link candidates.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser().resolve()
    out_root = Path(args.out_dir).expanduser().resolve()
    out = build_outputs(out_root)

    raw, ingest_report = ingest_all_weeks(data_dir)

    candidates = DEFAULT_NET_PAYOUT_CANDIDATES.copy()
    if args.net_payout_col.strip():
        candidates = [args.net_payout_col.strip().lower()] + [c for c in candidates if c != args.net_payout_col.strip().lower()]

    fact = build_fact_rider_week(raw, candidates)
    dim = build_dim_rider(fact)
    qa = build_qa_identity_conflicts(fact)
    qa_fuzzy = (
        build_qa_fuzzy_identity_links(fact, min_similarity=int(args.fuzzy_min_similarity))
        if args.fuzzy_linking_report
        else pd.DataFrame()
    )
    features = build_rider_features(fact)
    features = features.merge(dim[["rider_key", "cee_id", "rider_id", "cee_name", "pan", "city", "lmd_provider", "delivery_mode"]], on="rider_key", how="left")

    # Write outputs
    fact.sort_values(["year", "month", "week", "rider_key"]).to_csv(out.fact_rider_week, index=False)
    dim.sort_values(["rider_key"]).to_csv(out.dim_rider, index=False)
    qa.to_csv(out.qa_identity_conflicts, index=False)
    if args.fuzzy_linking_report:
        qa_fuzzy.to_csv(out.qa_fuzzy_identity_links, index=False)
    features.sort_values(["active_weeks_worked", "net_payout_mean"], ascending=[False, False]).to_csv(out.rider_features, index=False)
    ingest_report.to_csv(out.ingestion_file_report, index=False)

    print(f"Wrote outputs to: {out.out_dir}")
    print(f"- {out.fact_rider_week.name}")
    print(f"- {out.rider_features.name}")
    print(f"- {out.dim_rider.name}")
    print(f"- {out.qa_identity_conflicts.name}")
    if args.fuzzy_linking_report:
        print(f"- {out.qa_fuzzy_identity_links.name}")
    print(f"- {out.ingestion_file_report.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


