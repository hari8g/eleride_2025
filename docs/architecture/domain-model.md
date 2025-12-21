# Domain model (MVP)

This MVP persists only what’s needed to demo the flow.

## Tables

### `otp_challenges`

- `id` (uuid string)
- `phone`
- `otp_hash`
- `expires_at`
- `verified`

### `riders`

- `id` (uuid string)
- `phone` (unique)
- `name`, `dob`, `address`, `emergency_contact`, `preferred_zones`
- `status`: `NEW` → `PROFILE_COMPLETED` → `KYC_IN_PROGRESS` → `VERIFIED_PENDING_SUPPLY_MATCH`

### `supply_requests`

Represents “connect me” / lead creation and match result.

- `id`
- `rider_id`
- `lane_id`
- `operator_id` (matched)
- `pickup_location` (demo)
- `status`

### `commitments`

Backend-enforced lock.

- `id`
- `rider_id`
- `operator_id`
- `lane_id`
- `lock_mode`: `RESTRICT_TO_LANE` or `HIDE_ALL_DEMAND`
- `starts_at`, `ends_at`
- `status`: `ACTIVE` / `CANCELLED` / `COMPLETED` (MVP uses ACTIVE/CANCELLED)


