import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db
from app.domains.demand_ml.schemas import DemandImportIn, DemandImportOut
from app.domains.demand_ml.service import import_payout_xlsx_as_demand_proxy


router = APIRouter(prefix="/admin/demand")


@router.post("/import-from-docs", response_model=DemandImportOut)
def import_from_docs(payload: DemandImportIn, db: Session = Depends(get_db)) -> DemandImportOut:
    # MVP: in dev allow without admin auth so you can iterate quickly with the frontend.
    if settings.env != "dev":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enabled outside dev")

    docs_root = "/app/docs"
    xlsx_path = os.path.normpath(os.path.join(docs_root, payload.filename))
    if not xlsx_path.startswith(docs_root):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename path")
    if not os.path.exists(xlsx_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {payload.filename}")

    res = import_payout_xlsx_as_demand_proxy(db, xlsx_path=xlsx_path, sheet_name=payload.sheet_name)
    return DemandImportOut(
        rows_seen=res.rows_seen,
        aggregates_upserted=res.aggregates_upserted,
        forecasts_upserted=res.forecasts_upserted,
    )


