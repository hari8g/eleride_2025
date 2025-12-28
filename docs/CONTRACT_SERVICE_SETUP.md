# Contract Generation Service - Setup Guide

## Overview

The contract generation microservice automatically generates rider agreement contracts when a rider completes KYC verification. The contract is displayed in the rider app as a scrollable PDF.

## Architecture

1. **Contract Service** (`services/contract-service/`): FastAPI microservice that:
   - Takes rider data as JSON
   - Auto-fills DOCX template with placeholders
   - Converts to PDF (optional, requires LibreOffice)
   - Serves contracts via download endpoint

2. **Platform API Integration**: 
   - Generates contract when rider status becomes `VERIFIED_PENDING_SUPPLY_MATCH`
   - Stores contract URL in `rider.contract_url` field
   - Exposes `/riders/contract` endpoint

3. **Rider App Frontend**:
   - Shows contract step after KYC completion
   - Displays PDF in iframe
   - Allows download

## Local Testing

### 1. Start Services

```bash
cd /Users/harig/Desktop/Eleride

# Start all services (postgres, redis, platform-api, contract-service)
docker compose up -d

# Or start contract service separately
cd services/contract-service
uvicorn app.main:app --reload --port 8001
```

### 2. Verify Contract Service

```bash
# Health check
curl http://localhost:8001/health

# Inspect template placeholders
curl http://localhost:8001/template/inspect
```

### 3. Test Contract Generation

```bash
# Generate contract (returns JSON with filename)
curl -X POST http://localhost:8001/contracts/render \
  -H "Content-Type: application/json" \
  -d @services/contract-service/docs/sample_payload.json

# Generate PDF
curl -X POST http://localhost:8001/contracts/render/pdf \
  -H "Content-Type: application/json" \
  -d @services/contract-service/docs/sample_payload.json \
  --output test_contract.pdf
```

### 4. Test End-to-End Flow

1. Start rider app: `cd apps/rider-app && npm run dev`
2. Login with phone: `+919999000010`
3. Complete profile
4. Complete KYC verification
5. Contract should appear automatically
6. View contract in iframe
7. Download contract PDF

## Template Setup

The DOCX template is located at:
```
services/contract-service/templates/rider_agreement_template.docx
```

### Placeholder Format

All placeholders in the template must use format:
```
{{PLACEHOLDER_NAME}}
```

Example placeholders:
- `{{RIDER_NAME}}`
- `{{RIDER_AGE}}`
- `{{WEEKLY_RENTAL_INR}}`
- `{{AGREEMENT_CITY}}`
- `{{BANK_NAME}}`
- `{{ACCOUNT_NO}}`

### Supported Fields

See `services/contract-service/app/models.py` for complete list of fields.

## Database Migration

The `rider.contract_url` field was added. Run migration:

```bash
# If using Alembic (recommended)
alembic revision --autogenerate -m "add_contract_url_to_rider"
alembic upgrade head

# Or manually add column:
# ALTER TABLE riders ADD COLUMN contract_url VARCHAR;
```

## Configuration

### Environment Variables

**Contract Service:**
- `CONTRACT_SERVICE_URL`: URL of contract service (default: `http://localhost:8001`)

**Platform API:**
- Set `CONTRACT_SERVICE_URL=http://contract-service:8000` in docker-compose (already configured)

## PDF Conversion

PDF conversion requires LibreOffice to be installed:

```bash
# In Docker (already in Dockerfile)
apt-get install -y libreoffice

# On macOS (for local dev)
brew install --cask libreoffice
```

If LibreOffice is not available, the service falls back to serving DOCX files.

## API Endpoints

### Contract Service

- `GET /health` - Health check
- `GET /template/inspect` - List all placeholders in template
- `POST /contracts/render` - Generate DOCX contract
- `POST /contracts/render/pdf` - Generate PDF contract
- `GET /contracts/download/{filename}` - Download generated contract

### Platform API

- `GET /riders/me` - Get rider profile (includes `contract_url`)
- `GET /riders/contract` - Redirect to contract download

## Troubleshooting

### Contract not generating

1. Check contract service logs: `docker compose logs contract-service`
2. Verify template exists: `ls services/contract-service/templates/`
3. Check placeholder names match template
4. Verify LibreOffice is installed (for PDF)

### Contract not showing in rider app

1. Check rider status is `VERIFIED_PENDING_SUPPLY_MATCH`
2. Check `rider.contract_url` is set in database
3. Verify contract service is accessible from platform-api
4. Check browser console for errors

### PDF conversion failing

1. Verify LibreOffice is installed: `libreoffice --version`
2. Check file permissions on `generated/` directory
3. Review contract service logs for conversion errors

## Production Considerations

1. **Storage**: Save contracts to S3 or similar, not local filesystem
2. **Security**: Add authentication to contract service
3. **Caching**: Cache generated contracts to avoid regeneration
4. **Audit**: Log all contract generations
5. **E-sign**: Integrate e-signature service (DocuSign, etc.)

## Next Steps

- [ ] Add contract versioning
- [ ] Add contract expiration dates
- [ ] Integrate e-signature service
- [ ] Add contract templates for different agreement types
- [ ] Add contract analytics and tracking

