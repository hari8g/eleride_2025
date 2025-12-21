# Eleride Rider App (Prod-style Demo UI)

This is the rider-facing app UI (mobile-first) wired to `services/platform-api`.

## Run

From repo root:

```bash
cd apps/rider-app
npm install
npm run dev
```

Open `http://localhost:5176`.

## Configure API base (optional)

By default it calls `http://localhost:18080`.

To override:

- macOS/Linux:

```bash
export VITE_API_BASE_URL="http://localhost:18080"
npm run dev
```


