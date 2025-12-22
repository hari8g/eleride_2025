from pydantic import BaseModel, Field


class OTPRequestIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)


class OTPRequestOut(BaseModel):
    request_id: str
    expires_in_seconds: int


class OTPVerifyIn(BaseModel):
    request_id: str
    otp: str = Field(min_length=4, max_length=10)


class OTPVerifyOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


