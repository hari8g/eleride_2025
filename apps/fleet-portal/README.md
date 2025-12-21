# Eleride Fleet Portal (Multi-tenant Operator Dashboard)

This is the operator-facing web portal:

- Multi-tenant login/signup (OTP)
- Incoming rider interest inbox (from `/supply/requests`)
- Fleet vehicle management (registration number as vehicle ID)
- Telematics device binding + telemetry ingest (demo)
- Maintenance ticketing
- Role-based access control enforced by backend

## Run

```bash
cd apps/fleet-portal
npm install
npm run dev
```

Open `http://localhost:5177`.

## Tenant note (demo)

The rider flow currently assigns operator_id = `eleride-fleet`.

To see rider requests in the inbox immediately, create a tenant with:
- Operator name: `Eleride Fleet`
- (slug becomes `eleride-fleet`)


