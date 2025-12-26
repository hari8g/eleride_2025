## Cash flow underwriting – weekly payout feature builder

This repo ingests the weekly payout extracts in `Data/` and produces analysis-ready CSVs for building a cash-advance underwriting engine (continuity/streaks, payout mean/volatility, base vs incentive mix, orders and attendance).

### Setup

Create a virtual environment and install dependencies:

```bash
cd "/Users/harig/Desktop/Cash flow_underwriting"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run

```bash
cd "/Users/harig/Desktop/Cash flow_underwriting"
source .venv/bin/activate
python scripts/build_underwriting_features.py --data-dir Data --out-dir outputs
```

Optional: generate a conservative fuzzy identity-linking suggestion report for PAN-missing riders (for human review; it does **not** auto-merge riders):

```bash
python scripts/build_underwriting_features.py --data-dir Data --out-dir outputs --fuzzy-linking-report --fuzzy-min-similarity 95
```

### Underwriting engine (heuristics)

This reads the latest `outputs/run_*` folder and produces an offer sheet + portfolio summary.

Lender lens (salary-advance / EarlySalary-style):

```bash
source .venv/bin/activate
python scripts/underwriting_engine.py --outputs-root outputs --product salary_advance_lender
```

3PL lens (working-capital + partnership economics):

```bash
source .venv/bin/activate
python scripts/underwriting_engine.py --outputs-root outputs --product 3pl_operator
```

### Underwriting logic (detailed)

This section describes the **current decisioning logic** implemented in `scripts/underwriting_engine.py`.

#### Key definitions

- **Rider-week**: one row per rider per week (built from your Excel payout exports). See `outputs/run_*/fact_rider_week.csv`.
- **Rider features**: one row per rider with continuity + payout stats across weeks. See `outputs/run_*/rider_underwriting_features.csv`.
- **Offer**: underwriting decision + limit + repayment plan produced per rider. See `outputs_underwriting/uw_*/offers.csv`.

#### 1) Inputs used by the underwriting engine

The engine reads `outputs/run_*/rider_underwriting_features.csv` (built by `scripts/build_underwriting_features.py`). The main fields used are:

- **Continuity**
  - `active_weeks_worked`
  - `current_consecutive_active_weeks`
  - `weeks_since_last_active`
- **Payout distribution**
  - `net_payout_mean`, `net_payout_std`, `net_payout_cv`
  - `net_payout_p10` (downside safety)
- **Behavior**
  - `cancel_rate`

#### 2) Risk tiers (A/B/C/D)

Tiering is a deterministic heuristic using continuity + volatility:

- **Tier A**: recent active, long history, strong streak, low volatility
- **Tier B**: recent active, decent history/streak, moderate volatility
- **Tier C**: some recency tolerance, minimal acceptable history/streak, higher volatility tolerance
- **Tier D**: everything else (generally not offered if eligibility filters fail)

The exact tier assignment is in `assign_risk_tier()` in `scripts/underwriting_engine.py`.

#### 3) Eligibility rules (hard gates)

A rider is eligible only if they pass all hard filters:

- **Minimum history**: `active_weeks_worked >= min_active_weeks` (default 4)
- **Current streak**: `current_consecutive_active_weeks >= min_current_streak` (default 2)
- **Recency**: `weeks_since_last_active <= max_weeks_since_last_active` (default 0; i.e., must be active in most recent week)
- **Downside payout**: `net_payout_p10 >= min_net_payout_p10` (default ₹1500)
- **Behavior**: `cancel_rate <= max_cancel_rate` (default 0.08)

If declined, `offers.csv` contains a semicolon-separated `decline_reasons` string like:
`active_weeks_worked<4;net_payout_p10<1500`.

#### 4) Net payout forecast (weekly)

To size repayment capacity, we build a conservative weekly forecast from the rider’s payout distribution:

- \( \mu \) = `net_payout_mean`
- \( \sigma \) = `net_payout_std`
- \( p10 \) = `net_payout_p10`

Forecast:

\[
\text{payout\_forecast\_weekly}=\min(\mu,\ \mu-\alpha\sigma,\ p10)
\]

Where \( \alpha = \text{sigma_haircut} \) (default 0.75).

This intentionally biases toward downside outcomes (stability matters more than upside).

#### 5) Deductions, repayment plan, and limit sizing

Each tier has a maximum deduction share (and product-specific caps):

- Tier policy field: `max_deduction_share` (in `DEFAULT_TIERS`)
- In **3PL mode**, we additionally cap max deduction share at 25% to protect rider experience.

Compute:

1) **Collectible per week**

\[
\text{weekly\_collectible}=\text{max\_deduction\_share}\times\text{payout\_forecast\_weekly}
\]

2) **Raw limit** for a fixed repayment window (default 4 weeks)

\[
\text{raw\_limit}=\text{repayment\_weeks}\times\text{weekly\_collectible}
\]

3) **Haircuts**

We apply both a global haircut and a tier haircut:

\[
\text{recommended\_limit}=\text{raw\_limit}\times\text{base\_limit\_haircut}\times\text{tier\_limit\_haircut}
\]

4) **Minimum ticket + rounding**

- If `recommended_limit < min_ticket` (default ₹500): decline with reason `limit<500`
- Round down to nearest `round_to` (default ₹100)

5) **Weekly deduction**

\[
\text{recommended\_weekly\_deduction}=\frac{\text{recommended\_limit}}{\text{repayment\_weeks}}
\]

#### 6) Deduction % metrics (individual + portfolio)

In `offers.csv` we compute two rider-level metrics:

- **`deduction_pct_of_forecast_payout`**:
  \[
  \frac{\text{recommended\_weekly\_deduction}}{\text{payout\_forecast\_weekly}}
  \]
- **`deduction_pct_of_mean_payout`**:
  \[
  \frac{\text{recommended\_weekly\_deduction}}{\text{net\_payout\_mean}}
  \]

In `portfolio_summary.csv` we compute portfolio aggregates for **approved** riders:

- **Weighted share of forecast**:
  \[
  \frac{\sum \text{weekly\_deduction}}{\sum \text{payout\_forecast\_weekly}}
  \]
- Percentiles (p50/p90) of the rider-level deduction % distributions.

#### 7) Expected loss (PD/LGD/EAD)

We treat:

- **EAD**: `recommended_limit` (exposure at disbursal)
- **PD (term)**: tier-level heuristic `pd` from `DEFAULT_TIERS` stored as `pd_term`
- **LGD**: global `cfg.lgd` (default 0.35)

Per rider:

\[
\text{expected\_loss}=\text{EAD}\times\text{PD}\times\text{LGD}
\]

Portfolio totals are simple sums over approved riders.

Tier-wise counts/EAD/PD/LGD/EL are also produced in `portfolio_summary.csv` as:
`tier_A_count`, `tier_A_ead_sum`, `tier_A_pd_term`, `tier_A_lgd`, `tier_A_expected_loss_sum` (and similarly for B/C/D).

#### 8) APR policy (tier pricing)

APR per tier is defined in `DEFAULT_TIERS` (as decimals). Current defaults:

- Tier A: 35%
- Tier B: 40%
- Tier C: 45%
- Tier D: 36%

These APRs are written into `offers.csv` as `apr` and are used in the **Scenarios** page for revenue modeling.

#### 9) Portfolio summaries and 3PL working-capital summary

The engine emits:

- `portfolio_summary.csv`: approval rate, exposure (EAD), expected loss, deduction share, tier breakdown, and APR aggregates:
  - `repayment_weeks_mean`, `term_years_mean`
  - `apr_mean_approved`, `apr_weighted_by_ead`
- `3pl_working_capital_summary.csv` (3PL mode):
  - expected weekly advances (take-rate × approved riders)
  - expected weekly disbursal (take-rate × sum of limits)
  - referral fees + interest rev-share (simple interest approximation)
  - working capital freed estimate (disbursal shifted off 3PL balance sheet)

#### 10) “Required APR” (cost stack) on the Dashboard

On the dashboard Lender view, the **Required APR** panel computes the APR needed to cover:

- **COC** (input)
- **Annualized expected loss**
  - term EL rate = `expected_loss_sum / gross_exposure_sum`
  - annualized EL ≈ term EL / `term_years_mean`
- **Ops + CAC**
  - ops term rate = (approved riders × ops_per_disbursal) / EAD
  - annualized ops ≈ ops term rate / `term_years_mean`
- **Target margin** (input)

Then:

\[
\text{required\_APR}\approx \text{COC}+\text{EL}_{annual}+\text{Ops}_{annual}+\text{Margin}
\]

It also shows the current **APR weighted by EAD** (`apr_weighted_by_ead`) for comparison.

#### 11) Tuning knobs (what you change to calibrate policy)

In `scripts/underwriting_engine.py`:

- **Eligibility**: `min_active_weeks`, `min_current_streak`, `max_weeks_since_last_active`, `min_net_payout_p10`, `max_cancel_rate`
- **Forecast conservatism**: `sigma_haircut`
- **Term & repayment**: `repayment_weeks`
- **Limits**: tier `max_deduction_share`, `limit_haircut`, plus `base_limit_haircut`, `min_ticket`, `round_to`
- **Risk**: tier `pd` and global `lgd`
- **Pricing**: tier `apr`

#### 12) Important caveats

- This is a **heuristic underwriting engine**, not a statistically trained model.
- PD/LGD are placeholders until you observe repayment outcomes; treat EL as directional.
- Payout forecasting assumes the rider’s historical payout distribution is representative of near-term payouts.
- The scenario model uses a **simple interest approximation** and does not yet model repeat borrowing cohorts, roll-off, or interaction effects in sensitivity (OAT only).

### Frontend dashboard (single-page HTML)

1) Build `dashboard.json` (compiled from the latest `outputs/run_*` + `outputs_underwriting/`):

```bash
source .venv/bin/activate
python scripts/build_dashboard_json.py
```

2) Serve the frontend:

```bash
source .venv/bin/activate
python scripts/serve_dashboard.py --port 8000
```

If the port is already in use, either pick another port (e.g. `--port 8010`) or let it auto-pick a free port with `--port 0`.

Then open `http://127.0.0.1:8000` in your browser.

The frontend has two pages:

- `index.html`: dashboard (offers + portfolio summary)
- `scenarios.html`: scenario planning (portfolio-level cost economics & P&L, present vs future)

### Containerize as a microservice (separate portal)

This repo can run as a standalone “portal” container that serves the dashboard.

```bash
docker compose up --build
```

Open the portal at `http://127.0.0.1:8082`.

- The container rebuilds `frontend/data/dashboard.json` on startup from the latest `outputs/run_*` and `outputs_underwriting/*`.
- `docker-compose.yml` mounts `outputs/` and `outputs_underwriting/` as read-only volumes so you can refresh data without rebuilding the image.
- To connect this portal to another folder/service, add a second service in `docker-compose.yml` (an example is included and commented).

### Outputs

The script writes CSVs into `outputs/` (timestamped subfolder):

- `fact_rider_week.csv`: one row per rider per (year, month, week) after de-dup/aggregation.
- `rider_underwriting_features.csv`: one row per rider with activity counters, streaks, payout mean/volatility, mix metrics, recent-week features.
- `dim_rider.csv`: canonical rider identity fields (id/name/pan/city/provider/mode) plus QA stats.
- `qa_identity_conflicts.csv`: riders where `cee_name` / `pan` varies across weeks (useful for identity resolution auditing).
- `qa_fuzzy_identity_links.csv`: (optional) candidate pairs of riders with very similar names within the same city + delivery mode where PAN is missing.
- `ingestion_file_report.csv`: per-file ingestion stats and column availability.

Underwriting outputs are written into `outputs_underwriting/`:

- `offers.csv`: approve/decline + recommended limit + weekly deduction plan + tier + APR + decline reasons.
- `portfolio_summary.csv`: totals (approval rate, exposure, expected loss).
- `3pl_working_capital_summary.csv`: (3PL mode only) expected weekly disbursal, referral revenue, revenue share, and working-capital freed estimate.

### Notes

- Temp Excel lock files like `~$*.xlsx` are automatically ignored.
- If a rider appears multiple times in the same week (e.g., multiple `store` rows), the script **aggregates** to a single rider-week row by summing numeric metrics.

