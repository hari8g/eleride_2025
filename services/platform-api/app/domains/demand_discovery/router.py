from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_rider
from app.core.security import Principal
from app.domains.commitment_policy.service import check_access
from app.domains.demand_discovery.schemas import DemandNearbyOut
from app.domains.demand_discovery.service import CITY_CENTROIDS, build_cards_from_forecasts
from app.domains.demand_ml.models import StoreDemandRankingV2
from app.domains.rider.service import get_rider_by_phone
from app.domains.rider.models import RiderStatus


router = APIRouter(prefix="/demand")


@router.get("/nearby", response_model=DemandNearbyOut)
def nearby(
    lat: float,
    lon: float,
    radius_km: float = 5.0,
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> DemandNearbyOut:
    rider = get_rider_by_phone(db, principal.sub)
    if rider.status != RiderStatus.VERIFIED_PENDING_SUPPLY_MATCH:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "RIDER_NOT_VERIFIED", "required_status": RiderStatus.VERIFIED_PENDING_SUPPLY_MATCH.value},
        )

    decision = check_access(db, rider_id=rider.id, action="VIEW_DEMAND")

    def hav(lat1, lon1, lat2, lon2):
        import math

        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return r * c

    def detect_city(lat: float, lon: float) -> str:
        # Choose the closest known centroid if you're reasonably near it; otherwise default to Pune demo.
        best = None
        for city, (c_lat, c_lon) in CITY_CENTROIDS.items():
            d = hav(lat, lon, c_lat, c_lon)
            if best is None or d < best[0]:
                best = (d, city)
        # within ~90km -> treat as that city (Bangalore metro radius); else default to Pune so demos still work
        if best and best[0] <= 90.0:
            return best[1]
        return "PUNE"

    # Try to use real demand rankings from database
    rankings = db.query(StoreDemandRankingV2).all()
    
    if rankings:
        # Convert database rankings to forecast format
        forecasts = [
            {
                "city": r.city,
                "store": r.store,
                "orders_per_day": r.orders_per_day,
                "cancel_rate": r.cancel_rate,
                "incentive_share": r.incentive_share,
                "weekend_share": r.weekend_share,
                "demand_score": r.demand_score,
                "shift_start": r.shift_start,
                "contract_type": r.contract_type,
            }
            for r in rankings
        ]
        
        # Build cards from real forecasts
        cards = build_cards_from_forecasts(
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            forecasts=forecasts,
        )
    else:
        # Fallback to mock data if no rankings exist
        city = detect_city(lat, lon)
        if city in {"BENGALURU", "BANGALORE"}:
            cards = [
                {
                    "lane_id": "store:BANGALORE:KORAMANGALA",
                    "qc_name": "BANGALORE • Koramangala",
                    "lat": 12.9352,
                    "lon": 77.6245,
                    "distance_km": 0.0,
                    "shift_start": "07:00",
                    "earning_range": "₹650–₹950/day",
                    "minimum_guarantee": "₹550/day",
                    "expected_trips_per_day": 24,
                    "expected_orders_per_day": 52.0,
                    "contract_type": "WEEKLY",
                    "slots_available": "~4",
                    "rank_reasons": ["Dense drop zones", "Lunch peak"],
                },
                {
                    "lane_id": "store:BANGALORE:HSR",
                    "qc_name": "BANGALORE • HSR Layout",
                    "lat": 12.9116,
                    "lon": 77.6387,
                    "distance_km": 0.0,
                    "shift_start": "15:00",
                    "earning_range": "₹600–₹880/day",
                    "minimum_guarantee": "₹520/day",
                    "expected_trips_per_day": 21,
                    "expected_orders_per_day": 44.0,
                    "contract_type": "WEEKLY",
                    "slots_available": "~3",
                    "rank_reasons": ["Evening rush", "Good incentives"],
                },
                {
                    "lane_id": "store:BANGALORE:WHITEFIELD",
                    "qc_name": "BANGALORE • Whitefield",
                    "lat": 12.9698,
                    "lon": 77.7500,
                    "distance_km": 0.0,
                    "shift_start": "10:00",
                    "earning_range": "₹560–₹820/day",
                    "minimum_guarantee": "₹500/day",
                    "expected_trips_per_day": 19,
                    "expected_orders_per_day": 38.0,
                    "contract_type": "WEEKLY",
                    "slots_available": "~2",
                    "rank_reasons": ["Tech park demand", "Consistent weekdays"],
                },
            ]
        else:
            cards = [
                {
                    "lane_id": "store:PUNE:WAKAD",
                    "qc_name": "PUNE • Wakad",
                    "lat": 18.5975,
                    "lon": 73.7700,
                    "distance_km": 0.0,
                    "shift_start": "06:00",
                    "earning_range": "₹650–₹900/day",
                    "minimum_guarantee": "₹550/day",
                    "expected_trips_per_day": 22,
                    "expected_orders_per_day": 48.0,
                    "contract_type": "WEEKLY",
                    "slots_available": "~3",
                    "rank_reasons": ["High orders/day", "Low cancels"],
                },
                {
                    "lane_id": "store:PUNE:HINJEWADI",
                    "qc_name": "PUNE • Hinjewadi",
                    "lat": 18.5960,
                    "lon": 73.7400,
                    "distance_km": 0.0,
                    "shift_start": "14:00",
                    "earning_range": "₹600–₹850/day",
                    "minimum_guarantee": "₹520/day",
                    "expected_trips_per_day": 20,
                    "expected_orders_per_day": 42.0,
                    "contract_type": "WEEKLY",
                    "slots_available": "~2",
                    "rank_reasons": ["Weekend spike", "Good incentives"],
                },
                {
                    "lane_id": "store:PUNE:CHINCHWAD",
                    "qc_name": "PUNE • Chinchwad",
                    "lat": 18.6290,
                    "lon": 73.8000,
                    "distance_km": 0.0,
                    "shift_start": "10:00",
                    "earning_range": "₹550–₹780/day",
                    "minimum_guarantee": "₹500/day",
                    "expected_trips_per_day": 18,
                    "expected_orders_per_day": 36.0,
                    "contract_type": "WEEKLY",
                    "slots_available": "~2",
                    "rank_reasons": ["Consistent weekday demand"],
                },
            ]

    # Filter by radius (build_cards_from_forecasts already does this, but keep for mock data)
    if not rankings:
        filtered = []
        for c in cards:
            d = hav(lat, lon, c["lat"], c["lon"])
            cc = dict(c)
            cc["distance_km"] = round(d, 2)
            if d <= radius_km:
                filtered.append(cc)

        # If nothing falls in the radius, return all mock lanes with distances
        if not filtered:
            filtered = [
                {**c, "distance_km": round(hav(lat, lon, c["lat"], c["lon"]), 2)}
                for c in cards
            ]
    else:
        # Real data already filtered by build_cards_from_forecasts
        filtered = cards

    # Enforce commitment policy:
    # - HIDE_ALL_DEMAND => return empty cards + unlock time.
    # - RESTRICT_TO_LANE => only return the allowed lane.
    if not decision.allowed:
        return DemandNearbyOut(policy=decision.to_dict(), cards=[])
    if decision.allowed_lane_id:
        filtered = [c for c in filtered if c["lane_id"] == decision.allowed_lane_id]

    return DemandNearbyOut(policy=decision.to_dict(), cards=filtered)


