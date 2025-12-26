from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd


ProductType = Literal["salary_advance_lender", "3pl_operator"]


@dataclass(frozen=True)
class UnderwritingConfig:
    # Eligibility (hard filters)
    min_active_weeks: int = 4
    min_current_streak: int = 2
    max_weeks_since_last_active: int = 0
    min_net_payout_p10: float = 1500.0
    max_cancel_rate: float = 0.08

    # Repayment sizing (soft constraints)
    repayment_weeks: int = 4
    sigma_haircut: float = 0.75  # payout_forecast = min(mean, mean - sigma_haircut*std, p10)
    base_max_deduction_share: float = 0.25  # percent of weekly payout forecast allowed for recovery
    base_limit_haircut: float = 0.90  # haircut on theoretical limit
    min_ticket: float = 500.0
    round_to: int = 100

    # Pricing / yield stack (lender economics)
    # These are used to compute a floor APR that covers lender costs + target margin.
    cof_annual: float = 0.14  # cost of funds (annual)
    ops_per_disbursal: float = 40.0  # INR per approved disbursal
    target_margin_annual: float = 0.05  # target margin (annual)

    # Optional extra one-time margin fee (as % of principal) recovered via deductions
    margin_pct: float = 0.0  # e.g., 0.05 = 5% fee on principal

    # Risk mapping
    # Used for expected loss (illustrative defaults; tune with observed outcomes)
    lgd: float = 0.35  # with payout lock + collections rail, LGD should be low


@dataclass(frozen=True)
class RiskTierPolicy:
    tier: str
    max_deduction_share: float
    limit_haircut: float
    apr: float  # annual percentage rate, decimal (e.g. 0.18)
    pd: float  # probability of default over term (heuristic)


DEFAULT_TIERS: list[RiskTierPolicy] = [
    RiskTierPolicy(tier="A", max_deduction_share=0.30, limit_haircut=0.95, apr=0.35, pd=0.010),
    RiskTierPolicy(tier="B", max_deduction_share=0.27, limit_haircut=0.92, apr=0.40, pd=0.020),
    RiskTierPolicy(tier="C", max_deduction_share=0.25, limit_haircut=0.88, apr=0.45, pd=0.045),
    RiskTierPolicy(tier="D", max_deduction_share=0.22, limit_haircut=0.85, apr=0.36, pd=0.080),
]


def find_latest_run_dir(outputs_root: Path) -> Path:
    if not outputs_root.exists():
        raise FileNotFoundError(f"outputs root not found: {outputs_root}")
    runs = [p for p in outputs_root.iterdir() if p.is_dir() and p.name.startswith("run_")]
    if not runs:
        raise FileNotFoundError(f"No run_* folders found under: {outputs_root}")
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs[0]


def _coerce_float(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce").fillna(default).astype("float64")


def assign_risk_tier(row: pd.Series) -> str:
    active = int(row.get("active_weeks_worked", 0))
    streak = int(row.get("current_consecutive_active_weeks", 0))
    cv = float(row.get("net_payout_cv", 999))
    since = int(row.get("weeks_since_last_active", 999))

    if since == 0 and active >= 10 and streak >= 6 and cv <= 0.45:
        return "A"
    if since == 0 and active >= 6 and streak >= 3 and cv <= 0.75:
        return "B"
    if since <= 1 and active >= 4 and streak >= 2 and cv <= 1.10:
        return "C"
    return "D"


def tier_policy(tier: str, tiers: list[RiskTierPolicy]) -> RiskTierPolicy:
    for t in tiers:
        if t.tier == tier:
            return t
    return tiers[-1]


def payout_forecast_weekly(row: pd.Series, sigma_haircut: float) -> float:
    mean = float(row.get("net_payout_mean", 0.0))
    std = float(row.get("net_payout_std", 0.0))
    p10 = float(row.get("net_payout_p10", 0.0))

    # conservative forecast: take the minimum of central tendency and downside estimates
    candidates = [mean, mean - sigma_haircut * std, p10]
    val = float(np.nanmin(candidates))
    if not np.isfinite(val):
        val = 0.0
    return max(0.0, val)


def eligibility_and_reasons(row: pd.Series, cfg: UnderwritingConfig) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    active_weeks = int(row.get("active_weeks_worked", 0))
    streak = int(row.get("current_consecutive_active_weeks", 0))
    since = int(row.get("weeks_since_last_active", 999))
    cancel_rate = float(row.get("cancel_rate", 0.0))
    p10 = float(row.get("net_payout_p10", 0.0))

    if active_weeks < cfg.min_active_weeks:
        reasons.append(f"active_weeks_worked<{cfg.min_active_weeks}")
    if streak < cfg.min_current_streak:
        reasons.append(f"current_streak<{cfg.min_current_streak}")
    if since > cfg.max_weeks_since_last_active:
        reasons.append(f"weeks_since_last_active>{cfg.max_weeks_since_last_active}")
    if p10 < cfg.min_net_payout_p10:
        reasons.append(f"net_payout_p10<{cfg.min_net_payout_p10}")
    if cancel_rate > cfg.max_cancel_rate:
        reasons.append(f"cancel_rate>{cfg.max_cancel_rate}")

    eligible = len(reasons) == 0
    return eligible, reasons


def compute_offers(
    rider_features: pd.DataFrame,
    cfg: UnderwritingConfig,
    product: ProductType,
    tiers: list[RiskTierPolicy] = DEFAULT_TIERS,
) -> pd.DataFrame:
    df = rider_features.copy()

    # ensure important numeric fields exist
    for col in [
        "active_weeks_worked",
        "current_consecutive_active_weeks",
        "weeks_since_last_active",
        "net_payout_mean",
        "net_payout_std",
        "net_payout_p10",
        "cancel_rate",
    ]:
        if col not in df.columns:
            df[col] = 0

    df["risk_tier"] = df.apply(assign_risk_tier, axis=1)

    elig_flags = []
    reasons = []
    forecasts = []
    max_deduction = []
    limit = []
    weekly_deduction = []
    aprs = []
    pds = []
    lgds = []
    expected_loss = []
    ded_pct_forecast = []
    ded_pct_mean = []
    interest_amount = []
    margin_amount = []
    total_recovery = []
    apr_required = []
    apr_used = []
    el_annual_component = []
    ops_annual_component = []

    for _, row in df.iterrows():
        tier = str(row["risk_tier"])
        pol = tier_policy(tier, tiers)

        # product-specific tweaks (e.g., 3PL may choose lower deduction share for rider UX)
        if product == "3pl_operator":
            max_share = min(pol.max_deduction_share, 0.25)
            apr = pol.apr  # still compute to estimate interest economics in a partnership
        else:
            max_share = pol.max_deduction_share
            apr = pol.apr

        payout_fc = payout_forecast_weekly(row, sigma_haircut=cfg.sigma_haircut)
        eligible, rs = eligibility_and_reasons(row, cfg)

        collectible = max_share * payout_fc  # max weekly deduction allowed by policy

        # Determine APR floor needed to cover lender cost stack.
        # Annualize term EL and ops, similar to the dashboard cost-stack logic:
        # required_apr ≈ COF + (PD*LGD)/term_years + (ops/principal)/term_years + target_margin
        term_years = cfg.repayment_weeks / 52.0 if cfg.repayment_weeks > 0 else 0.0
        el_term_rate = pol.pd * cfg.lgd
        el_annual = (el_term_rate / term_years) if term_years > 0 else 0.0

        # Principal sizing must consider interest in weekly deduction. Since ops/principal depends on principal,
        # use a short fixed-point iteration for stable sizing.
        apr_base = float(apr)
        apr_floor = apr_base
        principal_max = 0.0
        ops_annual = 0.0
        for _iter in range(3):
            apr_floor = max(apr_base, cfg.cof_annual + el_annual + ops_annual + cfg.target_margin_annual)
            # total repayment factor (principal + interest over term + optional fee)
            repay_factor = 1.0 + (apr_floor * term_years) + cfg.margin_pct
            repay_factor = max(1e-6, repay_factor)
            # principal such that weekly_deduction <= collectible
            principal_max = (cfg.repayment_weeks * collectible) / repay_factor if cfg.repayment_weeks > 0 else 0.0
            # update ops annual component based on this principal
            ops_term_rate = (cfg.ops_per_disbursal / principal_max) if principal_max > 0 else 0.0
            ops_annual = (ops_term_rate / term_years) if term_years > 0 else 0.0

        raw_limit = principal_max
        offer_limit = cfg.base_limit_haircut * pol.limit_haircut * raw_limit
        offer_limit = max(0.0, offer_limit)

        # minimum viable ticket
        if offer_limit < cfg.min_ticket:
            eligible = False
            rs = rs + [f"limit<{cfg.min_ticket}"]

        # round ticket
        if cfg.round_to > 0:
            offer_limit = (offer_limit // cfg.round_to) * cfg.round_to

        # Calculate interest and margin to be recovered
        # Use the APR floor (covers COF + EL + ops + margin), but never below tier APR.
        apr_floor_final = max(apr_base, cfg.cof_annual + el_annual + ops_annual + cfg.target_margin_annual)
        interest = offer_limit * apr_floor_final * term_years  # simple interest over term
        margin = offer_limit * cfg.margin_pct  # margin as percentage of principal
        
        # Total recovery = principal + interest + margin
        total_recovery_amount = offer_limit + interest + margin
        
        # Weekly deduction recovers principal + interest + margin
        wk_ded = (total_recovery_amount / cfg.repayment_weeks) if cfg.repayment_weeks > 0 else 0.0

        # Deduction % vs payout (two lenses)
        mean_payout = float(row.get("net_payout_mean", 0.0))
        ded_pct_fc = float(wk_ded / payout_fc) if payout_fc > 0 else 0.0
        ded_pct_mn = float(wk_ded / mean_payout) if mean_payout > 0 else 0.0

        # expected loss (illustrative)
        pd_term = pol.pd
        el = offer_limit * pd_term * cfg.lgd

        elig_flags.append(int(eligible))
        reasons.append(";".join(rs))
        forecasts.append(float(payout_fc))
        max_deduction.append(float(max_share))
        limit.append(float(offer_limit))
        weekly_deduction.append(float(wk_ded))
        aprs.append(float(apr))
        pds.append(float(pd_term))
        lgds.append(float(cfg.lgd))
        expected_loss.append(float(el))
        ded_pct_forecast.append(ded_pct_fc)
        ded_pct_mean.append(ded_pct_mn)
        interest_amount.append(float(interest))
        margin_amount.append(float(margin))
        total_recovery.append(float(total_recovery_amount))
        apr_required.append(float(cfg.cof_annual + el_annual + ops_annual + cfg.target_margin_annual))
        apr_used.append(float(apr_floor_final))
        el_annual_component.append(float(el_annual))
        ops_annual_component.append(float(ops_annual))

    df["eligible"] = elig_flags
    df["decline_reasons"] = reasons
    df["payout_forecast_weekly"] = forecasts
    df["max_deduction_share"] = max_deduction
    df["recommended_limit"] = limit
    df["recommended_weekly_deduction"] = weekly_deduction
    df["apr"] = aprs
    df["pd_term"] = pds
    df["lgd"] = lgds
    df["expected_loss"] = expected_loss
    df["deduction_pct_of_forecast_payout"] = ded_pct_forecast
    df["deduction_pct_of_mean_payout"] = ded_pct_mean
    df["interest_amount"] = interest_amount
    df["margin_amount"] = margin_amount
    df["total_recovery"] = total_recovery
    df["apr_required"] = apr_required
    df["apr_used"] = apr_used
    df["el_annual_component"] = el_annual_component
    df["ops_annual_component"] = ops_annual_component
    df["product"] = product
    df["repayment_weeks"] = cfg.repayment_weeks

    # keep a clean “offer sheet” view up front
    front = [
        "product",
        "eligible",
        "risk_tier",
        "recommended_limit",
        "repayment_weeks",
        "recommended_weekly_deduction",
        "payout_forecast_weekly",
        "deduction_pct_of_forecast_payout",
        "deduction_pct_of_mean_payout",
        "max_deduction_share",
        "apr",
        "expected_loss",
        "decline_reasons",
        "cee_id",
        "rider_id",
        "cee_name",
        "pan",
        "city",
        "delivery_mode",
        "lmd_provider",
    ]
    existing_front = [c for c in front if c in df.columns]
    rest = [c for c in df.columns if c not in existing_front]
    return df[existing_front + rest]


def portfolio_summary(offers: pd.DataFrame) -> pd.DataFrame:
    df = offers.copy()
    df["recommended_limit"] = _coerce_float(df, "recommended_limit", 0.0)
    df["expected_loss"] = _coerce_float(df, "expected_loss", 0.0)
    df["payout_forecast_weekly"] = _coerce_float(df, "payout_forecast_weekly", 0.0)
    df["recommended_weekly_deduction"] = _coerce_float(df, "recommended_weekly_deduction", 0.0)
    df["deduction_pct_of_forecast_payout"] = _coerce_float(df, "deduction_pct_of_forecast_payout", 0.0)
    df["deduction_pct_of_mean_payout"] = _coerce_float(df, "deduction_pct_of_mean_payout", 0.0)
    df["apr"] = _coerce_float(df, "apr", 0.0)
    df["repayment_weeks"] = pd.to_numeric(df.get("repayment_weeks", 0), errors="coerce").fillna(0).astype(int)
    df["eligible"] = pd.to_numeric(df.get("eligible", 0), errors="coerce").fillna(0).astype(int)

    approved = df[df["eligible"] == 1].copy()

    # Term + pricing aggregates (useful for yield / APR reconciliation)
    repayment_weeks_mean = float(pd.to_numeric(approved.get("repayment_weeks", 0), errors="coerce").fillna(0).mean()) if len(approved) else 0.0
    term_years = float(repayment_weeks_mean / 52.0) if repayment_weeks_mean > 0 else 0.0
    apr_mean = float(pd.to_numeric(approved.get("apr", 0.0), errors="coerce").fillna(0.0).mean()) if len(approved) else 0.0
    ead_sum_for_weight = float(approved["recommended_limit"].sum()) if len(approved) else 0.0
    apr_weighted = (
        float((approved["apr"] * approved["recommended_limit"]).sum() / ead_sum_for_weight)
        if ead_sum_for_weight > 0
        else 0.0
    )

    def tier_stats(tier: str) -> dict[str, float]:
        tdf = approved[approved.get("risk_tier", "") == tier].copy() if "risk_tier" in approved.columns else approved.iloc[0:0].copy()
        ead = float(tdf["recommended_limit"].sum()) if not tdf.empty else 0.0
        el_sum = float(tdf["expected_loss"].sum()) if not tdf.empty else 0.0
        pd_term = float(pd.to_numeric(tdf.get("pd_term", 0.0), errors="coerce").fillna(0.0).mean()) if not tdf.empty else 0.0
        lgd = float(pd.to_numeric(tdf.get("lgd", 0.0), errors="coerce").fillna(0.0).mean()) if not tdf.empty else 0.0
        return {
            f"tier_{tier}_count": float(tdf.shape[0]),
            f"tier_{tier}_ead_sum": ead,
            f"tier_{tier}_pd_term": pd_term,
            f"tier_{tier}_lgd": lgd,
            f"tier_{tier}_expected_loss_sum": el_sum,
        }

    tier_block: dict[str, float] = {}
    for t in ["A", "B", "C", "D"]:
        tier_block.update(tier_stats(t))

    # Portfolio-level deduction % (weighted by payout forecast)
    total_ded = float(approved["recommended_weekly_deduction"].sum())
    total_fc = float(approved["payout_forecast_weekly"].sum())
    ded_share_weighted = float(total_ded / total_fc) if total_fc > 0 else 0.0

    # Distribution (unweighted rider-level)
    p50_fc = float(approved["deduction_pct_of_forecast_payout"].quantile(0.50)) if len(approved) else 0.0
    p90_fc = float(approved["deduction_pct_of_forecast_payout"].quantile(0.90)) if len(approved) else 0.0
    p50_mn = float(approved["deduction_pct_of_mean_payout"].quantile(0.50)) if len(approved) else 0.0
    p90_mn = float(approved["deduction_pct_of_mean_payout"].quantile(0.90)) if len(approved) else 0.0

    summary = {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "product": str(df.get("product", ["unknown"])[0]) if len(df) else "unknown",
        "riders_total": int(df.shape[0]),
        "riders_approved": int(approved.shape[0]),
        "approval_rate": float(approved.shape[0] / df.shape[0]) if df.shape[0] else 0.0,
        "gross_exposure_sum": float(approved["recommended_limit"].sum()),
        "avg_ticket": float(approved["recommended_limit"].mean()) if approved.shape[0] else 0.0,
        "expected_loss_sum": float(approved["expected_loss"].sum()),
        "expected_loss_rate": float(approved["expected_loss"].sum() / approved["recommended_limit"].sum())
        if approved["recommended_limit"].sum() > 0
        else 0.0,
        "repayment_weeks_mean": repayment_weeks_mean,
        "term_years_mean": term_years,
        "apr_mean_approved": apr_mean,
        "apr_weighted_by_ead": apr_weighted,
        "weekly_deduction_sum": total_ded,
        "weekly_payout_forecast_sum": total_fc,
        "deduction_share_weighted_of_forecast": ded_share_weighted,
        "deduction_pct_forecast_p50": p50_fc,
        "deduction_pct_forecast_p90": p90_fc,
        "deduction_pct_mean_p50": p50_mn,
        "deduction_pct_mean_p90": p90_mn,
        "tier_A": int((approved.get("risk_tier", "") == "A").sum()) if "risk_tier" in approved.columns else 0,
        "tier_B": int((approved.get("risk_tier", "") == "B").sum()) if "risk_tier" in approved.columns else 0,
        "tier_C": int((approved.get("risk_tier", "") == "C").sum()) if "risk_tier" in approved.columns else 0,
        "tier_D": int((approved.get("risk_tier", "") == "D").sum()) if "risk_tier" in approved.columns else 0,
    }
    summary.update({k: (int(v) if k.endswith("_count") else float(v)) for k, v in tier_block.items()})
    return pd.DataFrame([summary])


def threepl_working_capital_summary(
    offers: pd.DataFrame,
    take_rate: float = 0.40,  # fraction of approved riders who will actually draw an advance in a week
    referral_fee_per_advance: float = 125.0,  # INR
    revenue_share_of_interest: float = 0.20,  # 20% of interest earned
) -> pd.DataFrame:
    """
    Converts offer sheet to 3PL economics. This is intentionally simple and transparent.
    """
    approved = offers[offers["eligible"] == 1].copy()
    if approved.empty:
        return pd.DataFrame(
            [
                {
                    "as_of": datetime.now().isoformat(timespec="seconds"),
                    "approved_riders": 0,
                    "expected_weekly_advances": 0.0,
                    "expected_weekly_disbursal": 0.0,
                    "expected_weekly_referral_fee": 0.0,
                    "expected_interest_revenue_share_term": 0.0,
                    "working_capital_freed_estimate": 0.0,
                }
            ]
        )

    approved["recommended_limit"] = _coerce_float(approved, "recommended_limit", 0.0)
    approved["apr"] = _coerce_float(approved, "apr", 0.0)
    approved["repayment_weeks"] = pd.to_numeric(approved.get("repayment_weeks", 4), errors="coerce").fillna(4).astype(int)

    expected_weekly_advances = take_rate * approved.shape[0]
    expected_weekly_disbursal = take_rate * approved["recommended_limit"].sum()

    # Interest for one draw over the term (simple interest approximation)
    # interest = principal * apr * term_years
    term_years = (approved["repayment_weeks"].clip(lower=1) / 52.0).astype(float)
    expected_interest = (approved["recommended_limit"] * approved["apr"] * term_years).sum() * take_rate
    expected_interest_share = revenue_share_of_interest * expected_interest

    # Working capital freed = disbursal shifted to lender balance sheet instead of 3PL balance sheet
    wc_freed = expected_weekly_disbursal

    return pd.DataFrame(
        [
            {
                "as_of": datetime.now().isoformat(timespec="seconds"),
                "approved_riders": int(approved.shape[0]),
                "expected_weekly_advances": float(expected_weekly_advances),
                "expected_weekly_disbursal": float(expected_weekly_disbursal),
                "expected_weekly_referral_fee": float(expected_weekly_advances * referral_fee_per_advance),
                "expected_interest_revenue_share_term": float(expected_interest_share),
                "working_capital_freed_estimate": float(wc_freed),
                "assumption_take_rate": float(take_rate),
                "assumption_referral_fee_per_advance": float(referral_fee_per_advance),
                "assumption_revenue_share_of_interest": float(revenue_share_of_interest),
            }
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Heuristic underwriting engine on top of rider payout features.")
    parser.add_argument("--outputs-root", type=str, default="outputs", help="Root folder containing run_* feature outputs")
    parser.add_argument("--run-dir", type=str, default="", help="Optional explicit run_* folder to use (overrides auto-latest)")
    parser.add_argument("--out-dir", type=str, default="outputs_underwriting", help="Where to write underwriting outputs")
    parser.add_argument(
        "--product",
        type=str,
        default="salary_advance_lender",
        choices=["salary_advance_lender", "3pl_operator"],
        help="Which underwriting lens to compute offers for",
    )
    # core knobs
    parser.add_argument("--min-active-weeks", type=int, default=4)
    parser.add_argument("--min-current-streak", type=int, default=2)
    parser.add_argument("--min-net-payout-p10", type=float, default=1500.0)
    parser.add_argument("--max-cancel-rate", type=float, default=0.08)
    parser.add_argument("--repayment-weeks", type=int, default=4)
    parser.add_argument("--sigma-haircut", type=float, default=0.75)
    parser.add_argument("--min-ticket", type=float, default=500.0)
    parser.add_argument("--round-to", type=int, default=100)
    parser.add_argument("--margin-pct", type=float, default=0.0, help="Additional margin percentage on principal (e.g., 0.05 = 5%% margin)")
    parser.add_argument("--cof-annual", type=float, default=0.14, help="Cost of funds (annual, decimal). Example: 0.14")
    parser.add_argument("--ops-per-disbursal", type=float, default=40.0, help="Ops + CAC per disbursal (INR). Example: 40")
    parser.add_argument("--target-margin-annual", type=float, default=0.05, help="Target margin (annual, decimal). Example: 0.05")
    # 3PL economics knobs
    parser.add_argument("--take-rate", type=float, default=0.40)
    parser.add_argument("--referral-fee", type=float, default=125.0)
    parser.add_argument("--revenue-share", type=float, default=0.20)
    args = parser.parse_args()

    outputs_root = Path(args.outputs_root).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve() if args.run_dir.strip() else find_latest_run_dir(outputs_root)

    rider_path = run_dir / "rider_underwriting_features.csv"
    if not rider_path.exists():
        raise FileNotFoundError(f"Missing rider features file: {rider_path}")

    riders = pd.read_csv(rider_path)

    cfg = UnderwritingConfig(
        min_active_weeks=int(args.min_active_weeks),
        min_current_streak=int(args.min_current_streak),
        min_net_payout_p10=float(args.min_net_payout_p10),
        max_cancel_rate=float(args.max_cancel_rate),
        repayment_weeks=int(args.repayment_weeks),
        sigma_haircut=float(args.sigma_haircut),
        min_ticket=float(args.min_ticket),
        round_to=int(args.round_to),
        margin_pct=float(args.margin_pct),
        cof_annual=float(args.cof_annual),
        ops_per_disbursal=float(args.ops_per_disbursal),
        target_margin_annual=float(args.target_margin_annual),
    )

    product: ProductType = args.product  # type: ignore[assignment]
    offers = compute_offers(riders, cfg=cfg, product=product)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir).expanduser().resolve() / f"uw_{product}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    offers_path = out_dir / "offers.csv"
    summary_path = out_dir / "portfolio_summary.csv"
    offers.to_csv(offers_path, index=False)
    portfolio_summary(offers).to_csv(summary_path, index=False)

    if product == "3pl_operator":
        threepl_path = out_dir / "3pl_working_capital_summary.csv"
        threepl_working_capital_summary(
            offers,
            take_rate=float(args.take_rate),
            referral_fee_per_advance=float(args.referral_fee),
            revenue_share_of_interest=float(args.revenue_share),
        ).to_csv(threepl_path, index=False)

    print(f"Using run_dir: {run_dir}")
    print(f"Wrote underwriting outputs to: {out_dir}")
    print(f"- {offers_path.name}")
    print(f"- {summary_path.name}")
    if product == "3pl_operator":
        print(f"- 3pl_working_capital_summary.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


