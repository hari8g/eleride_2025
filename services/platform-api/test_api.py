#!/usr/bin/env python3
"""Minimal API test server for demand predictions only."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5176", "http://127.0.0.1:5176"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "service": "eleride-platform-api-test"}

# Try to import demand router
try:
    from app.domains.demand_discovery.router import router as demand_router
    app.include_router(demand_router)
    print("✅ Demand router loaded")
except Exception as e:
    print(f"⚠️  Could not load demand router: {e}")
    @app.get("/demand/nearby")
    def demand_nearby_mock():
        return {"policy": {"allowed": True}, "cards": []}

if __name__ == "__main__":
    import uvicorn
    print("Starting test API on port 18080...")
    print("This is a minimal version for testing demand predictions")
    uvicorn.run(app, host="0.0.0.0", port=18080)
