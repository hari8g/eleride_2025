from pydantic import BaseModel


class DataFilesOut(BaseModel):
    data_dir: str
    files: list[str]


class RiderOut(BaseModel):
    cee_id: str | None = None
    cee_name: str | None = None
    pan: str | None = None
    city: str | None = None
    store: str | None = None


class RidersOut(BaseModel):
    file: str
    count: int
    riders: list[RiderOut]


class PayslipIdentity(BaseModel):
    cee_id: str | None = None
    cee_name: str | None = None
    pan: str | None = None
    city: str | None = None
    store: str | None = None
    delivery_mode: str | None = None
    lmd_provider: str | None = None
    rate_card_id: str | None = None
    settlement_frequency: str | None = None
    period: str | None = None


class PayslipOps(BaseModel):
    delivered_orders: float = 0.0
    cancelled_orders: float = 0.0
    weekday_orders: float = 0.0
    weekend_orders: float = 0.0
    attendance: float = 0.0
    distance: float = 0.0


class PayslipPay(BaseModel):
    base_pay: float = 0.0
    incentive_total: float = 0.0
    arrears_amount: float = 0.0
    deductions_amount: float = 0.0
    management_fee: float = 0.0
    gst: float = 0.0
    final_with_gst: float = 0.0
    final_with_gst_minus_settlement: float = 0.0
    gross_earnings_est: float = 0.0
    net_payout: float = 0.0


class PayslipOut(BaseModel):
    identity: PayslipIdentity
    ops: PayslipOps
    pay: PayslipPay

