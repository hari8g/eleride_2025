import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.demand_ml.models import StoreDemandRankingV2, StoreWeekSignalV2
from app.utils.xlsx import read_sheet_as_rows


def _norm_col(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").strip().lower()).strip("_")


def _to_int(x: str) -> int:
    try:
        return int(float(x))
    except Exception:
        return 0


def _to_float(x: str) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


@dataclass(frozen=True)
class ImportResult:
    rows_seen: int
    aggregates_upserted: int
    forecasts_upserted: int


def import_payout_xlsx_as_demand_proxy(db: Session, *, xlsx_path: str, sheet_name: str = "Sheet1") -> ImportResult:
    """
    Reads the rider payout XLSX and derives store/week aggregates as a proxy for demand.

    Expected columns (normalized):
      year, month, week, city, store,
      delivered_orders, cancelled_orders, pickup_orders, weekday_orders, weekend_orders,
      incentivised_orders, attendance, distance
    """
    rows = read_sheet_as_rows(xlsx_path, sheet_name=sheet_name, max_rows=None)
    if not rows or len(rows) < 2:
        return ImportResult(rows_seen=0, aggregates_upserted=0, forecasts_upserted=0)

    header = [_norm_col(c) for c in rows[0]]
    col_idx = {name: i for i, name in enumerate(header) if name}

    required = [
        "year",
        "month",
        "week",
        "city",
        "store",
        "delivered_orders",
        "cancelled_orders",
        "pickup_orders",
        "weekday_orders",
        "weekend_orders",
        "incentivised_orders",
        "attendance",
        "distance",
    ]
    missing = [c for c in required if c not in col_idx]
    if missing:
        raise ValueError(f"XLSX missing required columns: {missing}. Found: {sorted(col_idx.keys())}")

    # Aggregate across riders into store/week totals before writing.
    rows_seen = 0
    agg: dict[tuple[int, int, int, str, str], dict[str, float]] = {}
    for r in rows[1:]:
        if not r or len(r) < len(header):
            continue
        rows_seen += 1

        year = _to_int(r[col_idx["year"]])
        month = _to_int(r[col_idx["month"]])
        week = _to_int(r[col_idx["week"]])
        city = (r[col_idx["city"]] or "").strip()
        store = (r[col_idx["store"]] or "").strip()
        if not (year and month and week and city and store):
            continue

        delivered = _to_int(r[col_idx["delivered_orders"]])
        cancelled = _to_int(r[col_idx["cancelled_orders"]])
        pickup = _to_int(r[col_idx["pickup_orders"]])
        weekday = _to_int(r[col_idx["weekday_orders"]])
        weekend = _to_int(r[col_idx["weekend_orders"]])
        incentivised = _to_int(r[col_idx["incentivised_orders"]])
        attendance_days = _to_float(r[col_idx["attendance"]])
        distance_km = _to_float(r[col_idx["distance"]])

        key = (year, month, week, city, store)
        bucket = agg.setdefault(
            key,
            {
                "delivered": 0.0,
                "cancelled": 0.0,
                "pickup": 0.0,
                "weekday": 0.0,
                "weekend": 0.0,
                "incentivised": 0.0,
                "attendance": 0.0,
                "distance": 0.0,
            },
        )
        bucket["delivered"] += float(delivered)
        bucket["cancelled"] += float(cancelled)
        bucket["pickup"] += float(pickup)
        bucket["weekday"] += float(weekday)
        bucket["weekend"] += float(weekend)
        bucket["incentivised"] += float(incentivised)
        bucket["attendance"] += float(attendance_days)
        bucket["distance"] += float(distance_km)

    aggregates_upserted = 0
    for (year, month, week, city, store), bucket in agg.items():
        delivered = int(bucket["delivered"])
        cancelled = int(bucket["cancelled"])
        pickup = int(bucket["pickup"])
        weekday = int(bucket["weekday"])
        weekend = int(bucket["weekend"])
        incentivised = int(bucket["incentivised"])
        attendance_days = float(bucket["attendance"])
        distance_km = float(bucket["distance"])

        existing = (
            db.query(StoreWeekSignalV2)
            .filter(
                StoreWeekSignalV2.year == year,
                StoreWeekSignalV2.month == month,
                StoreWeekSignalV2.week == week,
                StoreWeekSignalV2.city == city,
                StoreWeekSignalV2.store == store,
            )
            .one_or_none()
        )
        if existing is None:
            db.add(
                StoreWeekSignalV2(
                    year=year,
                    month=month,
                    week=week,
                    city=city,
                    store=store,
                    delivered_orders=delivered,
                    cancelled_orders=cancelled,
                    pickup_orders=pickup,
                    weekday_orders=weekday,
                    weekend_orders=weekend,
                    incentivised_orders=incentivised,
                    distance_km=distance_km,
                    attendance_days=attendance_days,
                )
            )
            aggregates_upserted += 1
        else:
            existing.delivered_orders = delivered
            existing.cancelled_orders = cancelled
            existing.pickup_orders = pickup
            existing.weekday_orders = weekday
            existing.weekend_orders = weekend
            existing.incentivised_orders = incentivised
            existing.distance_km = distance_km
            existing.attendance_days = attendance_days

    db.commit()

    forecasts_upserted = materialize_rankings_v2(db)
    return ImportResult(rows_seen=rows_seen, aggregates_upserted=aggregates_upserted, forecasts_upserted=forecasts_upserted)


def materialize_rankings_v2(db: Session) -> int:
    """
    Heuristic ranking model (store-level):
    - orders/day: delivered / max(attendance_days, 1)
    - cancel_rate: cancelled / (delivered+cancelled)
    - incentive_share: incentivised / max(delivered, 1)
    - weekend_share: weekend / max(weekday+weekend, 1)
    Score emphasizes throughput, penalizes cancellations, and lightly boosts incentive/weekend share.
    """
    rows = db.query(StoreWeekSignalV2).all()
    if not rows:
        return 0

    # group by store/city
    groups: dict[tuple[str, str], list[StoreWeekSignalV2]] = {}
    for r in rows:
        groups.setdefault((r.city, r.store), []).append(r)

    def sort_key(x: StoreWeekSignalV2):
        return (x.year, x.month, x.week)

    upserted = 0
    now = datetime.now(timezone.utc)
    for (city, store), items in groups.items():
        items.sort(key=sort_key)

        # Recency-weighted aggregation of base metrics (still a heuristic, not "forecasting")
        alpha = 0.70
        w_sum = 0.0
        orders_per_day = 0.0
        cancel_rate = 0.0
        incentive_share = 0.0
        weekend_share = 0.0
        for i, it in enumerate(items):
            w = (1 - alpha) * (alpha ** (len(items) - 1 - i))
            w_sum += w

            days = it.attendance_days if it.attendance_days and it.attendance_days > 0 else 7.0
            opd = float(it.delivered_orders) / float(max(days, 1.0))

            total = float(it.delivered_orders + it.cancelled_orders)
            cr = float(it.cancelled_orders) / float(total) if total > 0 else 0.0

            inc = float(it.incentivised_orders) / float(max(it.delivered_orders, 1))

            ww_total = float(it.weekday_orders + it.weekend_orders)
            ws = float(it.weekend_orders) / float(ww_total) if ww_total > 0 else 0.0

            orders_per_day += w * opd
            cancel_rate += w * cr
            incentive_share += w * inc
            weekend_share += w * ws

        if w_sum > 0:
            orders_per_day /= w_sum
            cancel_rate /= w_sum
            incentive_share /= w_sum
            weekend_share /= w_sum

        # Score
        # Throughput is king; cancellations are heavily penalized.
        demand_score = (
            1.0 * orders_per_day
            + 0.35 * orders_per_day * incentive_share
            + 0.15 * orders_per_day * weekend_share
            - 1.25 * orders_per_day * cancel_rate
        )

        existing = (
            db.query(StoreDemandRankingV2)
            .filter(StoreDemandRankingV2.city == city, StoreDemandRankingV2.store == store)
            .one_or_none()
        )
        if existing is None:
            existing = StoreDemandRankingV2(
                city=city,
                store=store,
                demand_score=demand_score,
                orders_per_day=orders_per_day,
                cancel_rate=cancel_rate,
                incentive_share=incentive_share,
                weekend_share=weekend_share,
                updated_at=now,
            )
            db.add(existing)
            upserted += 1
        else:
            existing.demand_score = demand_score
            existing.orders_per_day = orders_per_day
            existing.cancel_rate = cancel_rate
            existing.incentive_share = incentive_share
            existing.weekend_share = weekend_share
            existing.updated_at = now

    db.commit()
    return upserted


