# Quick Start Guide - Eleride Platform

## All Services Running ✅

### Backend Services
- **Platform API**: http://localhost:18080
  - API Docs: http://localhost:18080/docs
  - Health: http://localhost:18080/health

- **Contract Service**: http://localhost:8002
  - Health: http://localhost:8002/health
  - Template Inspect: http://localhost:8002/template/inspect

- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

### Frontend Apps
- **Rider App**: http://localhost:5176
- **Fleet Portal**: http://localhost:5177
- **Financing Portal**: http://localhost:5178
- **Maintenance Tech**: http://localhost:5179
- **Matchmaking Portal**: http://localhost:5180

## Quick Commands

### Start All Services
```bash
cd /Users/harig/Desktop/Eleride
docker compose up -d
```

### Stop All Services
```bash
docker compose down
```

### View Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f platform-api
docker compose logs -f contract-service
```

### Restart a Service
```bash
docker compose restart platform-api
docker compose restart contract-service
```

## Testing Contract Generation

### Test Contract Service Directly
```bash
curl -X POST http://localhost:8002/contracts/render \
  -H "Content-Type: application/json" \
  -d @services/contract-service/docs/sample_payload.json
```

### Test End-to-End Flow
1. Open Rider App: http://localhost:5176
2. Login with phone: `+919999000010`
3. Complete profile
4. Complete KYC verification
5. Contract will be generated automatically
6. View contract in the app

## Fleet Portal - Vehicle Management

### Import Vehicles from Excel
```bash
cd /Users/harig/Desktop/Eleride
echo "yes" | python3 scripts/import_vehicles_simple.py
```

### Access Fleet Portal
1. Open: http://localhost:5177
2. Login with phone: `+919999000401`
3. Use dev OTP from backend logs
4. View all 534 imported vehicles
5. Navigate pages using pagination

## Database Notes

The `contract_url` field was added to the `riders` table. If you get migration errors:

```sql
ALTER TABLE riders ADD COLUMN contract_url VARCHAR;
```

## Troubleshooting

### Service Not Starting
```bash
# Check status
docker compose ps

# Check logs
docker compose logs [service-name]

# Restart
docker compose restart [service-name]
```

### Contract Service Issues
- Verify template exists: `ls services/contract-service/templates/`
- Check LibreOffice is installed in container (for PDF conversion)
- Test health endpoint: `curl http://localhost:8002/health`

### Platform API Issues
- Verify pandas is installed: `docker compose exec platform-api pip list | grep pandas`
- Check database connection
- Verify environment variables in `env.local`

## Development URLs

- **API Documentation**: http://localhost:18080/docs
- **Contract Service API**: http://localhost:8002/docs (if FastAPI docs enabled)

