# API contracts (MVP)

All rider endpoints require `Authorization: Bearer <token>` except OTP request/verify.

## Identity

- `POST /auth/otp/request`
  - body: `{ "phone": "..." }`
  - returns: `{ request_id, expires_in_seconds, dev_otp? }`

- `POST /auth/otp/verify`
  - body: `{ "request_id": "...", "otp": "......" }`
  - returns: `{ access_token, token_type }`

## Rider

- `POST /riders/profile`
- `GET /riders/me`
- `GET /riders/status`

## KYC (mock)

- `POST /riders/kyc/start`
- `POST /riders/kyc/complete-pass`

## Demand discovery (policy gated)

- `GET /demand/nearby?lat=..&lon=..&radius_km=5`
  - returns: `{ policy, cards }`
  - if locked: `423 LOCKED` with `{ detail: { code: "LOCKED", unlock_at, ... } }`

## Supply connect (“connect me”)

- `POST /supply/requests`
  - body: `{ lane_id, time_window?, requirements? }`
  - returns: operator onboarding payload + pickup info

## Commitment policy

- `POST /commitments`
- `GET /commitments/active`
- `POST /commitments/{id}/cancel` (admin only; stubbed RBAC)


