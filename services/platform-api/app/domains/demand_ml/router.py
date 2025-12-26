import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db
from app.domains.demand_ml.models import StoreDemandRankingV2, StoreWeekSignalV2
from app.domains.demand_ml.schemas import DemandImportIn, DemandImportOut
from app.domains.demand_ml.service import import_payout_xlsx_as_demand_proxy


router = APIRouter(prefix="/admin/demand")


@router.post("/import-from-docs", response_model=DemandImportOut)
def import_from_docs(payload: DemandImportIn, db: Session = Depends(get_db)) -> DemandImportOut:
    # Enable in production - can be secured with admin auth later if needed
    # For now, allow import in both dev and prod environments
    
    # Support both /app/docs (legacy) and /app/cashflow_data (current) directories
    docs_roots = ["/app/docs", "/app/cashflow_data"]
    xlsx_path = None
    
    for docs_root in docs_roots:
        candidate_path = os.path.normpath(os.path.join(docs_root, payload.filename))
        if candidate_path.startswith(docs_root) and os.path.exists(candidate_path):
            xlsx_path = candidate_path
            break
    
    if xlsx_path is None:
        # Try to find the file in any of the allowed directories
        for docs_root in docs_roots:
            if os.path.exists(docs_root):
                candidate_path = os.path.normpath(os.path.join(docs_root, payload.filename))
                if candidate_path.startswith(docs_root) and os.path.exists(candidate_path):
                    xlsx_path = candidate_path
                    break
    
    if xlsx_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {payload.filename}. Searched in: {', '.join(docs_roots)}"
        )

    res = import_payout_xlsx_as_demand_proxy(db, xlsx_path=xlsx_path, sheet_name=payload.sheet_name)
    return DemandImportOut(
        rows_seen=res.rows_seen,
        aggregates_upserted=res.aggregates_upserted,
        forecasts_upserted=res.forecasts_upserted,
    )


@router.get("/status")
def get_status(db: Session = Depends(get_db)) -> dict:
    """Get status of demand prediction model data."""
    signals_count = db.query(StoreWeekSignalV2).count()
    rankings_count = db.query(StoreDemandRankingV2).count()
    
    # Get sample of top rankings
    top_rankings = (
        db.query(StoreDemandRankingV2)
        .order_by(StoreDemandRankingV2.demand_score.desc())
        .limit(5)
        .all()
    )
    
    sample_rankings = [
        {
            "city": r.city,
            "store": r.store,
            "demand_score": r.demand_score,
            "orders_per_day": r.orders_per_day,
            "cancel_rate": r.cancel_rate,
        }
        for r in top_rankings
    ]
    
    return {
        "signals_count": signals_count,
        "rankings_count": rankings_count,
        "has_data": rankings_count > 0,
        "top_rankings": sample_rankings,
    }


