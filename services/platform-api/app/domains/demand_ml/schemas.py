from pydantic import BaseModel, Field


class DemandImportIn(BaseModel):
    filename: str = Field(min_length=3, max_length=256, description="Path under /app/docs (e.g. 'ELERIDE ... .xlsx')")
    sheet_name: str = Field(default="Sheet1", max_length=64)


class DemandImportOut(BaseModel):
    ok: bool = True
    rows_seen: int
    aggregates_upserted: int
    forecasts_upserted: int


