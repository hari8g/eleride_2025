from dataclasses import dataclass


@dataclass(frozen=True)
class OperatorRecommendation:
    operator_id: str
    name: str
    pickup_location: str
    required_docs: list[str]


def pick_operator_for_lane(*, lane_id: str, operator_id: str | None = None) -> OperatorRecommendation:
    """
    MVP operator “profile” provider for the rider UX.
    - If operator_id is provided, use it (name is prettified).
    - Otherwise, fall back to a default operator.
    """
    op = operator_id or "eleride-fleet"
    # Prettify slug -> name (demo)
    name = " ".join([w.capitalize() for w in op.replace("_", "-").split("-") if w]) or op
    pickup = f"{name} Hub (demo)"
    return OperatorRecommendation(operator_id=op, name=name, pickup_location=pickup, required_docs=["DL", "Aadhaar/PAN"])


