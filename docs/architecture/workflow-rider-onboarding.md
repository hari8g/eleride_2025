# Rider entry → demand discovery → connect → onboarding → commitment lock (MVP)

This document describes the **end-to-end workflow** implemented in `services/platform-api` and the **bounded contexts** you can later extract into microservices.

## State machine (rider verification)

Statuses live on `riders.status`:

- `NEW`: created after OTP verify
- `PROFILE_COMPLETED`: profile captured
- `KYC_IN_PROGRESS`: started KYC
- `VERIFIED_PENDING_SUPPLY_MATCH`: KYC pass → eligible to connect to supply

Commitment lock is **not** a rider.status; it’s enforced by `commitment_policy` using `commitments` records.

## Sequence (happy path)

```mermaid
sequenceDiagram
  participant RiderApp as Rider App
  participant API as Platform API (BFF)
  participant Identity as Identity (OTP/JWT)
  participant Rider as Rider
  participant KYC as KYC Orchestrator (mock)
  participant Policy as Commitment Policy
  participant Demand as Demand Discovery
  participant Supply as Supply Connect
  participant Match as Supply Match (mock)

  RiderApp->>Identity: POST /auth/otp/request
  Identity-->>RiderApp: request_id (+ dev_otp in dev)
  RiderApp->>Identity: POST /auth/otp/verify
  Identity-->>RiderApp: JWT

  RiderApp->>Rider: POST /riders/profile (JWT)
  Rider-->>RiderApp: PROFILE_COMPLETED

  RiderApp->>KYC: POST /riders/kyc/start (JWT)
  KYC-->>RiderApp: KYC_IN_PROGRESS
  RiderApp->>KYC: POST /riders/kyc/complete-pass (JWT)
  KYC-->>RiderApp: VERIFIED_PENDING_SUPPLY_MATCH

  RiderApp->>Policy: checkAccess(VIEW_DEMAND)
  Policy-->>Demand: decision(allowed / restricted / locked)
  RiderApp->>Demand: GET /demand/nearby?lat&lon&radius_km (JWT)
  Demand-->>RiderApp: cards + policy

  RiderApp->>Supply: POST /supply/requests (lane_id) (JWT)
  Supply->>Match: pick operator (mock)
  Supply-->>RiderApp: operator onboarding step + pickup location

  RiderApp->>Policy: POST /commitments (lane_id, operator_id, 7 days)
  Policy-->>RiderApp: commitment created (starts now)

  RiderApp->>Demand: GET /demand/nearby (JWT)
  Demand-->>RiderApp: either locked OR restricted-to-lane feed (backend enforced)
```

## Commitment lock enforcement

Every demand feed call executes:

1. `check_access(rider_id, action="VIEW_DEMAND")`
2. If locked → return `423 LOCKED` with `unlock_at`
3. If restricted → return only the committed `lane_id`

This is a **hard backend gate**, not UI-only.

## Bounded contexts (microservice candidates)

Currently implemented as domain modules inside a single FastAPI app:

- `identity`: OTP challenge + JWT issuance
- `rider`: profile + verification state
- `kyc`: mocked KYC transitions (vendor integration later)
- `demand_discovery`: returns sanitized demand cards (geo + caching later)
- `supply_match`: selects eligible operator candidates (optimizer later)
- `supply`: “connect me” request creation + onboarding handoff payload
- `commitment_policy`: rule enforcement + commitment lifecycle


