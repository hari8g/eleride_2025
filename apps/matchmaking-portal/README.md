# Eleride Matchmaking Portal (Console)

This app visualizes the **auto-assignment moat**:
- Multi-operator live availability (`/matchmaking/availability`)
- Explainable recommendation (`/matchmaking/recommend`)

## Run

```bash
cd apps/matchmaking-portal
npm install
npm run dev
```

Open `http://localhost:5180`.

Notes:
- MVP auth uses **Rider OTP** (same as rider-app) so it can call rider-auth endpoints.
- In production, this would be restricted to internal/admin roles.


