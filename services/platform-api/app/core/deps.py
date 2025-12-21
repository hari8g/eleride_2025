from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.security import Principal, decode_bearer_token


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_principal(request: Request) -> Principal:
    auth = request.headers.get("authorization") or ""
    prefix = "bearer "
    if not auth.lower().startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = auth[len(prefix) :].strip()
    try:
        return decode_bearer_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_rider(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.role != "rider":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rider role required")
    return principal


def require_operator(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.role != "operator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator role required")
    if not principal.operator_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator tenant missing")
    return principal


def require_operator_roles(allowed: set[str]):
    def _inner(principal: Principal = Depends(require_operator)) -> Principal:
        if principal.operator_role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient operator role")
        return principal

    return _inner


def require_lessor(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.role != "lessor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lessor role required")
    if not principal.lessor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lessor tenant missing")
    return principal


def require_lessor_roles(allowed: set[str]):
    def _inner(principal: Principal = Depends(require_lessor)) -> Principal:
        if principal.lessor_role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient lessor role")
        return principal

    return _inner


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return principal


