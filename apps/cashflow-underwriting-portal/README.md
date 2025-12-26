## Cashflow Underwriting Portal (static)

This is a **static** portal that renders `data/dashboard.json` produced by the cashflow underwriting pipeline.

### Local run

- Option 1 (quick): open `index.html` in a browser (works best via a local server).
- Option 2 (recommended): serve via Python:

```bash
cd apps/cashflow-underwriting-portal
python3 -m http.server 8092
```

Open `http://127.0.0.1:8092`.

### Data contract

The portal fetches:
- `data/dashboard.json` (cache-busted with a `?t=` query param)

This is the contract we’ll keep stable so we can later move generation/hosting behind an API (Option B) without rewriting the UI.


