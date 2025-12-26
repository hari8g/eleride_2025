# Eleride — Rider Entry → Demand Discovery → Connect → Onboarding → Commitment Lock (MVP)

This repo scaffolds **only** the workflow you described:

- **Rider entry** (phone + OTP, profile capture)
- **Demand discovery** (nearby cards, “just enough info”)
- **Connect me** (creates a supply/onboarding lead)
- **Onboarding handoff** (to a fleet operator)
- **Commitment lock** (backend-enforced 7-day lock that gates demand access)

It’s implemented as a **modular monolith** (single FastAPI app) with **clear bounded-context modules** that can be extracted into microservices later.

## Repo layout

```
.
  docker-compose.yml
  env.example
  apps/
    rider-app/                  # rider-facing (mobile-first) app UI
    fleet-portal/               # multi-tenant operator dashboard (fleet management)
    financing-portal/           # financing dashboard (buy-back underwriting + portfolio analytics)
    matchmaking-portal/         # internal console (multi-operator availability + explainable auto-assign)
  services/
    platform-api/              # modular monolith (FastAPI)
  docs/
    architecture/
      workflow-rider-onboarding.md
      domain-model.md
      api-contracts.md
```

## Quickstart (local)

1) Copy env:

```bash
cp env.example env.local
```

2) Start services:

```bash
docker compose up --build
```

3) Open API docs:

- `http://localhost:18080/docs`

## Local dev (backend + all frontends)

This starts Postgres + Redis + API (Docker) and all Vite apps (Node) with the API base set to `http://localhost:18080`.

```bash
./scripts/dev-local.sh
```

### Dev OTP (recommended for local)

In `env.local`, set:

```bash
OTP_DEV_MODE=true
```

To stop the backend containers:

```bash
./scripts/dev-stop.sh
```

## Rider App (prod-style demo UI)

Start the rider app:

```bash
cd apps/rider-app
npm install
npm run dev
```

Then open `http://localhost:5176`.

## Fleet Portal (multi-tenant operator dashboard)

```bash
cd apps/fleet-portal
npm install
npm run dev
```

Then open `http://localhost:5177`.

## Financing Portal (buy-back underwriting dashboard)

```bash
cd apps/financing-portal
npm install
npm run dev
```

Then open `http://localhost:5178`.

## What’s implemented

- **Identity**: OTP request/verify (MVP/in-memory OTP store) + JWT auth
- **Rider**: profile + status
- **KYC**: mocked “start” + “complete” to transition to `VERIFIED_PENDING_SUPPLY_MATCH`
- **Demand discovery**: returns demo demand cards, filtered/blocked by policy
- **Supply match**: trivial operator selection (placeholder)
- **Commitment policy**: creates commitments, enforces a **hard backend gate** on demand access

## What to extract into microservices later

The code is already organized as if these were services:

- `identity`
- `rider`
- `kyc`
- `demand_discovery`
- `supply_match`
- `commitment_policy`

When you’re ready, you can split each router + domain logic into its own deployable service behind a gateway/BFF.


