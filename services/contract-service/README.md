# Contract Generation Service

FastAPI microservice for generating rider agreement contracts from DOCX templates.

## Features

- Auto-fills DOCX templates with rider onboarding data
- Supports placeholder replacement in paragraphs, tables, headers, and footers
- Optional PDF conversion via LibreOffice
- RESTful API for integration
- Template inspection endpoint for ops verification

## Setup

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Place your DOCX template in `templates/rider_agreement_template.docx`

3. Run the service:
```bash
uvicorn app.main:app --reload --port 8001
```

### Docker

```bash
docker build -t contract-service .
docker run -p 8001:8000 contract-service
```

## API Endpoints

### GET /health
Health check endpoint.

### GET /template/inspect
Inspect template and list all placeholders found.

**Response:**
```json
{
  "template_path": "templates/rider_agreement_template.docx",
  "template_exists": true,
  "placeholders_found": ["RIDER_NAME", "RIDER_AGE", ...],
  "placeholder_count": 15
}
```

### POST /contracts/render
Generate contract DOCX from template.

**Request Body:**
```json
{
  "agreement_city": "Mumbai",
  "agreement_date_long": "January 15, 2025",
  "rider_name": "John Doe",
  "rider_age": 25,
  "rider_address": "123 Main St, Mumbai",
  "weekly_rental_inr": 1500.00,
  "security_deposit_inr": 5000.00,
  "account_holder_name": "Eleride Fleet",
  "bank_name": "HDFC Bank",
  "account_no": "1234567890",
  "ifsc": "HDFC0001234",
  "branch": "Mumbai Main"
}
```

**Response:**
```json
{
  "success": true,
  "filename": "rider_agreement_20250115_120000_abc12345.docx",
  "message": "Contract generated successfully",
  "file_size_bytes": 45678
}
```

### GET /contracts/download/{filename}
Download generated contract file.

### POST /contracts/render/pdf
Generate contract and convert to PDF (requires LibreOffice).

## Placeholder Format

All placeholders in the DOCX template must be in format:
```
{{PLACEHOLDER_NAME}}
```

Example placeholders:
- `{{RIDER_NAME}}`
- `{{RIDER_AGE}}`
- `{{WEEKLY_RENTAL_INR}}`
- `{{AGREEMENT_CITY}}`

## Supported Fields

### Required Fields
- `agreement_city`: City where agreement is signed
- `rider_name`: Full name of rider
- `rider_age`: Age (must be 18+)
- `rider_address`: Complete address
- `weekly_rental_inr`: Weekly rental amount
- `security_deposit_inr`: Security deposit amount
- `account_holder_name`: Bank account holder name
- `bank_name`: Bank name
- `account_no`: Account number
- `ifsc`: IFSC code
- `branch`: Branch name

### Optional Fields
- `rider_father_name`: Father's name
- `rider_id`: ID number (Aadhaar/PAN)
- `family_name`, `family_phone`: Family contact
- `friend_name`, `friend_phone`: Friend contact
- `extra_placeholders`: Dict for additional custom placeholders

## Example Usage

### cURL Example

```bash
curl -X POST "http://localhost:8001/contracts/render" \
  -H "Content-Type: application/json" \
  -d '{
    "agreement_city": "Mumbai",
    "rider_name": "John Doe",
    "rider_age": 25,
    "rider_address": "123 Main St, Mumbai",
    "weekly_rental_inr": 1500.00,
    "security_deposit_inr": 5000.00,
    "account_holder_name": "Eleride Fleet",
    "bank_name": "HDFC Bank",
    "account_no": "1234567890",
    "ifsc": "HDFC0001234",
    "branch": "Mumbai Main"
  }'
```

### Python Example

```python
import requests

payload = {
    "agreement_city": "Mumbai",
    "rider_name": "John Doe",
    "rider_age": 25,
    "rider_address": "123 Main St, Mumbai",
    "weekly_rental_inr": 1500.00,
    "security_deposit_inr": 5000.00,
    "account_holder_name": "Eleride Fleet",
    "bank_name": "HDFC Bank",
    "account_no": "1234567890",
    "ifsc": "HDFC0001234",
    "branch": "Mumbai Main"
}

response = requests.post("http://localhost:8001/contracts/render", json=payload)
result = response.json()
print(f"Generated: {result['filename']}")
```

## Testing

Run tests:
```bash
pytest tests/
```

## Legal Safety

⚠️ **Important**: This service only replaces placeholders in templates. It does NOT:
- Modify legal text
- Generate new clauses
- Infer legal terms
- Compute indemnity language

The template is the source of truth for all legal content.

