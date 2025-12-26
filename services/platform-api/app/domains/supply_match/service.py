from dataclasses import dataclass


@dataclass(frozen=True)
class OperatorRecommendation:
    operator_id: str
    name: str
    pickup_location: str
    pickup_lat: float
    pickup_lon: float
    required_docs: list[str]


def pickup_hub_for_operator(operator_id: str) -> tuple[str, float, float]:
    """
    MVP pickup hub lookup.
    In production this should come from an Operator profile table.
    """
    op = (operator_id or "eleride-fleet").strip().lower()
    # NOTE: this function is intentionally MVP; we infer city from lane_id in pick_operator_for_lane.
    # Keep Pune as default so existing flows continue to work.
    if op in {"eleride-fleet", "fleet", "eleride"}:
        return "Eleride Fleet Hub • Pune (demo)", 18.5626, 73.9168  # Kharadi-ish
    if op in {"maint", "maintenance-tech", "maintenance"}:
        return "Eleride Maintenance Yard • Pune (demo)", 18.5960, 73.7460  # Hinjewadi-ish
    if op in {"financing", "financing-portal", "leasing"}:
        return "Eleride Finance Desk • Pune (demo)", 18.5362, 73.8940  # Koregaon Park-ish
    return "Eleride Fleet Hub • Pune (demo)", 18.5626, 73.9168


def _city_from_lane_id(lane_id: str | None) -> str:
    """
    lane_id format: store:<CITY>:<STORE> (e.g., store:BANGALORE:KORAMANGALA)
    """
    if not lane_id:
        return "PUNE"
    parts = [p.strip().upper() for p in str(lane_id).split(":") if p.strip()]
    city = parts[1] if len(parts) >= 2 else "PUNE"
    if city in {"BENGALURU", "BLR"}:
        return "BANGALORE"
    return city


def pickup_hub_for_operator_and_city(operator_id: str, city: str) -> tuple[str, float, float]:
    op = (operator_id or "eleride-fleet").strip().lower()
    c = (city or "").strip().upper()
    if c in {"BENGALURU", "BLR"}:
        c = "BANGALORE"

    # Bangalore hubs (demo)
    if c == "BANGALORE":
        if op in {"eleride-fleet", "fleet", "eleride"}:
            return "Eleride Fleet Hub • Bangalore (demo)", 12.9569, 77.7011  # Marathahalli-ish
        if op in {"maint", "maintenance-tech", "maintenance"}:
            return "Eleride Maintenance Yard • Bangalore (demo)", 12.9352, 77.6245  # Koramangala-ish
        if op in {"financing", "financing-portal", "leasing"}:
            return "Eleride Finance Desk • Bangalore (demo)", 12.9716, 77.5946  # Central
        return "Eleride Fleet Hub • Bangalore (demo)", 12.9569, 77.7011

    # Pune default
    return pickup_hub_for_operator(operator_id)


def pick_operator_for_lane(*, lane_id: str, operator_id: str | None = None) -> OperatorRecommendation:
    """
    MVP operator “profile” provider for the rider UX.
    - If operator_id is provided, use it (name is prettified).
    - Otherwise, fall back to a default operator.
    """
    op = operator_id or "eleride-fleet"
    # Prettify slug -> name (demo)
    name = " ".join([w.capitalize() for w in op.replace("_", "-").split("-") if w]) or op
    city = _city_from_lane_id(lane_id)
    pickup, plat, plon = pickup_hub_for_operator_and_city(op, city)
    return OperatorRecommendation(
        operator_id=op,
        name=name,
        pickup_location=pickup,
        pickup_lat=float(plat),
        pickup_lon=float(plon),
        required_docs=["DL", "Aadhaar/PAN"],
    )


