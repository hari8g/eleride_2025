"""
Demand Prediction Model (Store-Week) — Training Script
-----------------------------------------------------

Reads a payout Excel, aggregates rider-level rows into STORE-WEEK demand rows,
trains a scikit-learn model, and saves it for inference.

Works best with MULTIPLE weeks of data. With a single week, it will train but warn
about limited forecasting quality (no lag/time splits).

Default input: ./docs/ELERIDE IBBN Payout Sep 25 WEEK 4.xlsx
Outputs:
  - demand_model.joblib
  - training_metrics.json
  - feature_importance.csv (if available)
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


# ----------------------------
# CONFIG
# ----------------------------
# Get project root (3 levels up from this script: scripts/demand-model/)
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_MODELS_DIR = PROJECT_ROOT / "data" / "models"

DEFAULT_INPUT = PROJECT_ROOT / "docs" / "ELERIDE IBBN Payout Sep 25 WEEK 4.xlsx"
MODEL_OUT = DATA_MODELS_DIR / "demand_model.joblib"
METRICS_OUT = DATA_MODELS_DIR / "training_metrics.json"
FI_OUT = DATA_MODELS_DIR / "feature_importance.csv"


# ----------------------------
# UTILS
# ----------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower())


def find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    norm_map = {_norm(c): c for c in df.columns}
    for cand in candidates:
        key = _norm(cand)
        if key in norm_map:
            return norm_map[key]
    norm_cols = {_norm(c): c for c in df.columns}
    for cand in candidates:
        key = _norm(cand)
        for ncol, orig in norm_cols.items():
            if key in ncol or ncol in key:
                return orig
    return None


def coerce_numeric(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series
    s = series.astype(str).str.replace(",", "", regex=False)
    s = s.str.replace(r"[^\d\.\-]", "", regex=True)
    return pd.to_numeric(s, errors="coerce")


def safe_sum(df: pd.DataFrame, cols: List[str]) -> pd.Series:
    present = [c for c in cols if c in df.columns]
    if not present:
        return pd.Series([0.0] * len(df), index=df.index)
    x = df[present].apply(coerce_numeric)
    return x.sum(axis=1, skipna=True)


def infer_week_id(df: pd.DataFrame) -> pd.Series:
    week_col = find_col(df, ["cw", "week", "week_no", "week number", "calendar_week"])
    if week_col:
        w = df[week_col].astype(str).str.strip()
        num = w.str.extract(r"(\d+)", expand=False)
        num = pd.to_numeric(num, errors="coerce")
        return num.fillna(0).astype(int)

    year_col = find_col(df, ["year"])
    month_col = find_col(df, ["month"])
    wk_col2 = find_col(df, ["wk", "week_no", "weekno"])
    if year_col and month_col and wk_col2:
        y = pd.to_numeric(df[year_col], errors="coerce").fillna(0).astype(int)
        m = pd.to_numeric(df[month_col], errors="coerce").fillna(0).astype(int)
        w = pd.to_numeric(df[wk_col2], errors="coerce").fillna(0).astype(int)
        return (y * 10000 + m * 100 + w).astype(int)

    return pd.Series([0] * len(df), index=df.index, dtype=int)


def add_store_week_lags(
    store_week: pd.DataFrame, group_key: str, time_key: str, target_col: str, lags: List[int] = [1, 2, 4]
) -> pd.DataFrame:
    out = store_week.sort_values([group_key, time_key]).copy()
    g = out.groupby(group_key, sort=False)
    for k in lags:
        out[f"{target_col}_lag_{k}"] = g[target_col].shift(k)
    out[f"{target_col}_roll_mean_4"] = g[target_col].shift(1).rolling(4).mean().reset_index(level=0, drop=True)
    out[f"{target_col}_roll_std_4"] = g[target_col].shift(1).rolling(4).std().reset_index(level=0, drop=True)
    out[f"{target_col}_trend_1"] = out[f"{target_col}_lag_1"] - out[f"{target_col}_lag_2"]
    return out


# ----------------------------
# DATA PREP
# ----------------------------
def build_store_week_table(df: pd.DataFrame) -> Tuple[pd.DataFrame, str, str]:
    city_col = find_col(df, ["city"])
    store_col = find_col(df, ["store", "store_name", "store id", "store_id"])
    store_type_col = find_col(df, ["store_type", "store type"])
    mode_col = find_col(df, ["delivery_mode", "delivery mode", "mode"])
    provider_col = find_col(df, ["lmd_provider", "provider", "3pl", "3pl_name", "fleet_operator"])
    rate_col = find_col(df, ["rate_card_id", "rate card id", "rate_card", "ratecard"])

    rider_id_col = find_col(df, ["cee_id", "rider_id", "rider id", "driver_id", "captain_id", "rider"])

    delivered_col = find_col(df, ["delivered_orders", "delivered orders", "delivered"])
    cancelled_col = find_col(df, ["cancelled_orders", "canceled_orders", "cancelled orders", "cancelled"])
    pickup_col = find_col(df, ["pickup_orders", "pickup orders", "pickup"])

    attendance_col = find_col(df, ["attendance"])
    distance_col = find_col(df, ["distance", "kms", "km"])
    service_time_col = find_col(df, ["service_time", "service time", "service_minutes", "service mins"])

    mg_col = find_col(df, ["minimum_guarantee", "minimum guarantee", "mg", "min_guarantee"])
    mg_days_col = find_col(df, ["mg_eligible_days", "mg eligible days", "eligible days"])

    df = df.copy()
    df["week_id"] = infer_week_id(df)

    for c in [delivered_col, cancelled_col, pickup_col, attendance_col, distance_col, service_time_col, mg_col, mg_days_col]:
        if c and c in df.columns:
            df[c] = coerce_numeric(df[c])

    payout_cols = [c for c in df.columns if "payout" in _norm(c)]
    extra_money_like = [c for c in df.columns if any(k in _norm(c) for k in ["surge", "incentive", "peak", "bonus", "guarantee"])]
    money_cols = sorted(set(payout_cols + extra_money_like))

    group_cols = []
    for c in [city_col, store_col, store_type_col, mode_col, provider_col, rate_col]:
        if c and c in df.columns:
            group_cols.append(c)
    if not group_cols:
        if store_col and store_col in df.columns:
            group_cols = [store_col]
        else:
            raise ValueError("Could not identify grouping columns like 'store'/'city'. Please check column names.")

    group_cols_time = group_cols + ["week_id"]

    if delivered_col and delivered_col in df.columns:
        target_col = "y_delivered_orders"
        df[target_col] = df[delivered_col].fillna(0.0)
    else:
        raise ValueError("Could not find 'delivered_orders' column (or similar). Please verify the sheet headers.")

    df["x_cancelled_orders"] = df[cancelled_col].fillna(0.0) if cancelled_col and cancelled_col in df.columns else 0.0
    df["x_pickup_orders"] = df[pickup_col].fillna(0.0) if pickup_col and pickup_col in df.columns else 0.0

    df["x_attendance"] = df[attendance_col].fillna(0.0) if attendance_col and attendance_col in df.columns else 0.0
    df["x_distance"] = df[distance_col].fillna(0.0) if distance_col and distance_col in df.columns else 0.0
    df["x_service_time"] = df[service_time_col].fillna(0.0) if service_time_col and service_time_col in df.columns else 0.0

    df["x_minimum_guarantee"] = df[mg_col].fillna(0.0) if mg_col and mg_col in df.columns else 0.0
    df["x_mg_eligible_days"] = df[mg_days_col].fillna(0.0) if mg_days_col and mg_days_col in df.columns else 0.0

    if money_cols:
        df["x_total_payout_like"] = safe_sum(df, money_cols).fillna(0.0)
    else:
        df["x_total_payout_like"] = 0.0

    # Build named aggregations (pandas >= 1.0)
    agg_dict: Dict[str, tuple] = {}
    agg_dict[target_col] = (target_col, "sum")
    agg_dict["x_cancelled_orders"] = ("x_cancelled_orders", "sum")
    agg_dict["x_pickup_orders"] = ("x_pickup_orders", "sum")
    agg_dict["x_attendance"] = ("x_attendance", "sum")
    agg_dict["x_distance"] = ("x_distance", "sum")
    agg_dict["x_service_time"] = ("x_service_time", "sum")
    agg_dict["x_minimum_guarantee"] = ("x_minimum_guarantee", "sum")
    agg_dict["x_mg_eligible_days"] = ("x_mg_eligible_days", "sum")
    agg_dict["x_total_payout_like"] = ("x_total_payout_like", "sum")

    if rider_id_col and rider_id_col in df.columns:
        agg_dict["x_active_riders"] = (rider_id_col, pd.Series.nunique)
    else:
        agg_dict["x_active_riders"] = (target_col, "count")

    store_week = df.groupby(group_cols_time, dropna=False).agg(**agg_dict).reset_index()

    store_week["x_orders_per_active_rider"] = store_week[target_col] / np.maximum(store_week["x_active_riders"].astype(float), 1.0)
    store_week["x_cancel_rate"] = store_week["x_cancelled_orders"] / np.maximum(
        (store_week[target_col] + store_week["x_cancelled_orders"]), 1.0
    )

    if store_col and store_col in store_week.columns:
        store_week["store_key"] = store_week[store_col].astype(str)
    else:
        store_week["store_key"] = store_week[group_cols].astype(str).agg("|".join, axis=1)

    store_week = add_store_week_lags(store_week, group_key="store_key", time_key="week_id", target_col=target_col)

    return store_week, "week_id", target_col


# ----------------------------
# TRAIN
# ----------------------------
def train_model(store_week: pd.DataFrame, time_col: str, target_col: str) -> Tuple[Pipeline, dict, pd.DataFrame]:
    store_week = store_week.copy()
    store_week = store_week[store_week[target_col].notna()].reset_index(drop=True)

    drop_cols = {target_col}
    candidate_features = [c for c in store_week.columns if c not in drop_cols]

    cat_cols = [c for c in candidate_features if store_week[c].dtype == "object"]
    num_cols = [c for c in candidate_features if c not in cat_cols and c != target_col]

    X = store_week[candidate_features]
    y = store_week[target_col].astype(float)

    numeric_pipe = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])
    categorical_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, num_cols),
            ("cat", categorical_pipe, cat_cols),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )

    model = HistGradientBoostingRegressor(loss="poisson", learning_rate=0.05, max_depth=6, max_iter=400, random_state=42)

    pipe = Pipeline(steps=[("prep", preprocessor), ("model", model)])

    periods = store_week[time_col].nunique()
    metrics = {
        "rows": int(len(store_week)),
        "unique_periods": int(periods),
        "target": target_col,
        "note": "",
    }

    if periods < 4:
        metrics["note"] = (
            "Not enough time periods to do time-series CV. "
            "Model will be fit on all data; accuracy metrics will be optimistic/undefined. "
            "Provide multiple weeks (ideally 12+)."
        )
        pipe.fit(X, y)
        metrics["mae_cv_mean"] = None
        metrics["wape_cv_mean"] = None
        fi_df = pd.DataFrame()
        return pipe, metrics, fi_df

    n_splits = min(5, periods - 1)
    tscv = TimeSeriesSplit(n_splits=n_splits)

    maes = []
    wapes = []

    order = np.argsort(store_week[time_col].values)
    X_sorted = X.iloc[order].reset_index(drop=True)
    y_sorted = y.iloc[order].reset_index(drop=True)

    for train_idx, test_idx in tscv.split(X_sorted):
        X_tr, X_te = X_sorted.iloc[train_idx], X_sorted.iloc[test_idx]
        y_tr, y_te = y_sorted.iloc[train_idx], y_sorted.iloc[test_idx]

        pipe_cv = joblib.loads(joblib.dumps(pipe))
        pipe_cv.fit(X_tr, y_tr)
        pred = pipe_cv.predict(X_te)
        pred = np.clip(pred, 0, None)

        mae = mean_absolute_error(y_te, pred)
        denom = float(np.sum(np.abs(y_te)))
        wape = float(np.sum(np.abs(y_te - pred)) / denom) if denom > 0 else np.nan

        maes.append(float(mae))
        wapes.append(float(wape))

    metrics["mae_cv_mean"] = float(np.mean(maes))
    metrics["mae_cv_std"] = float(np.std(maes))
    metrics["wape_cv_mean"] = float(np.nanmean(wapes))
    metrics["wape_cv_std"] = float(np.nanstd(wapes))

    pipe.fit(X, y)

    try:
        feat_names = pipe.named_steps["prep"].get_feature_names_out()
        fi_df = pd.DataFrame({"feature": feat_names})
    except Exception:
        fi_df = pd.DataFrame()

    return pipe, metrics, fi_df


# ----------------------------
# MAIN
# ----------------------------
def main(input_path: str = None):
    if input_path is None:
        input_path = str(DEFAULT_INPUT)
    else:
    input_path = str(input_path)
    
    # Ensure output directory exists
    DATA_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input not found: {input_path}")

    print(f"[1/5] Reading: {input_path}")
    df = pd.read_excel(input_path)

    print(f"[2/5] Building store-week table...")
    store_week, time_col, target_col = build_store_week_table(df)

    store_week = store_week[store_week["store_key"].notna()].reset_index(drop=True)

    print(f"[3/5] Training model... rows={len(store_week)}, periods={store_week[time_col].nunique()}")
    model, metrics, fi_df = train_model(store_week, time_col, target_col)

    print(f"[4/5] Saving model → {MODEL_OUT}")
    joblib.dump(model, str(MODEL_OUT))

    print(f"[5/5] Saving metrics → {METRICS_OUT}")
    with open(str(METRICS_OUT), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    if not fi_df.empty:
        fi_df.to_csv(str(FI_OUT), index=False)
        print(f"Saved feature names → {FI_OUT}")

    print("\nDone.")
    print("Metrics:")
    print(json.dumps(metrics, indent=2))

    print("\nExample predictions (last 5 rows):")
    X_last = store_week.drop(columns=[target_col], errors="ignore").tail(5)
    preds = model.predict(X_last)
    preds = np.clip(preds, 0, None)
    out = store_week.tail(5).copy()
    out["predicted_delivered_orders"] = preds
    cols_show = [c for c in ["week_id", "store_key", target_col, "predicted_delivered_orders"] if c in out.columns]
    print(out[cols_show].to_string(index=False))


if __name__ == "__main__":
    main()


