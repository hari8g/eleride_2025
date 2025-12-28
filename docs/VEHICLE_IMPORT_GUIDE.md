# Vehicle Import and Fleet Portal Setup Guide

This guide explains how to import vehicles from Excel and use the updated fleet portal with VIN-based identification.

## Changes Made

### Backend Changes
1. ✅ Added vehicle detail endpoint: `GET /operator/vehicles/{vehicle_id}`
2. ✅ Vehicle metadata now stores all registration details including VIN, brand, model, variant, color, reg date, chassis number, mfg year, owner name
3. ✅ Support for battery ID, battery number, location, and city fields

### Frontend Changes
1. ✅ **VIN Display**: Vehicle list now shows VIN instead of registration number in the "VIN" column
2. ✅ **Detailed Vehicle View**: When clicking "Open" on a vehicle, shows comprehensive registration details:
   - Registration Information (Brand, Model, Variant, Color, VIN, Reg Number, Reg Date, Chassis Number, mfg Year, RC Owner Name)
   - Battery Information (Battery ID, Battery Number)
   - Location (Location, City, Current Arena)
   - Additional information (any other fields from Excel)
3. ✅ **Location Display**: Shows location/city from metadata or current arena based on telemetry
4. ✅ **Vehicle Count**: Dashboard displays total vehicle count and statistics

## Setup Steps

### 1. Start Backend Services (Local)

```bash
# From project root
cd /Users/harig/Desktop/Eleride

# Start Docker services (Postgres, Redis, API)
docker compose up -d

# Or use the dev script
./scripts/dev-local.sh
```

The API will be available at: `http://localhost:18080`

### 2. Install Dependencies (if needed)

```bash
# Install openpyxl for Excel reading (if not already installed)
pip install openpyxl requests

# Or if using the platform-api virtual environment:
cd services/platform-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Import Vehicles from Excel

```bash
# From project root
cd /Users/harig/Desktop/Eleride

# Run the import script
python3 scripts/import_vehicles_simple.py
```

The script will:
- Read `data/Vehicle Inventory Data-271225xlsx.xlsx`
- Parse all vehicle data (VIN, registration details, battery info, location)
- Authenticate with the API (uses dev OTP)
- Create vehicles in the database
- Store all details in vehicle metadata

**Note**: If a vehicle already exists (same registration number), it will be skipped.

### 4. Start Fleet Portal Frontend

```bash
# From project root
cd apps/fleet-portal

# Install dependencies (first time only)
npm install

# Start development server
npm run dev
```

The fleet portal will be available at: `http://localhost:5177`

### 5. Login to Fleet Portal

1. Open `http://localhost:5177` in your browser
2. Use phone: `+919999000401`
3. Operator slug: `eleride-fleet`
4. Click "Send OTP"
5. Enter the dev OTP shown (or check console/API logs)
6. Click "Verify & Enter portal"

### 6. View Vehicles

1. **Portfolio Tab**: See vehicle count and statistics
2. **Vehicles Tab**: See all vehicles with VIN displayed
3. **Click "Open"** on any vehicle to see detailed registration information

## Excel File Format

The script expects these columns (case-insensitive, flexible naming):
- `VIN` or `Vehicle Identification Number`
- `Reg Number` or `Registration Number` or `Reg No`
- `Brand` or `Make`
- `Model`
- `Variant` or `Trim`
- `Color` or `Colour`
- `Reg Date` or `Registration Date`
- `Chassis Number` or `Chassis`
- `mfg Year` or `Manufacturing Year` or `Year`
- `RC Owner Name` or `Owner Name`
- `Battery ID`
- `Battery Number`
- `Location`
- `City`

## Vehicle Data Structure

Each vehicle stores data in the `meta` JSON field:
```json
{
  "vin": "VOMHPUA0001",
  "registration_number": "MH14JC4591",
  "brand": "Hero Electric",
  "model": "NYX ER",
  "variant": "ELECTRIC(BOV)",
  "color": "Silver",
  "reg_date": "24-03-2020",
  "chassis_number": "M9EJNHH219H000245",
  "mfg_year": "2020",
  "rc_owner_name": "ELERIDE MOBILITY SOLUTIONS PVT LTD",
  "battery_id": "BAT-001",
  "battery_number": "12345",
  "location": "Pune Warehouse",
  "city": "Pune"
}
```

## Frontend Features

### Vehicle List View
- Shows **VIN** in the first column (instead of registration number)
- Displays Arena/Location based on metadata or telemetry
- Shows Status, Battery %, Last seen, Odo
- "Open" button to view details

### Vehicle Detail View
When you click "Open" on a vehicle, you'll see:
1. **Registration Information** table with:
   - Brand, Model, Variant, Color
   - VIN, Reg Number, Reg Date
   - Chassis Number, mfg Year
   - RC Owner Name

2. **Battery Information** (if available):
   - Battery ID
   - Battery Number

3. **Location** (if available):
   - Location from metadata
   - City from metadata
   - Current Arena (from telemetry)

4. **Additional Information** (any other fields)

## Troubleshooting

### Import Script Fails

**Error: "ModuleNotFoundError: No module named 'openpyxl'"**
```bash
pip install openpyxl requests
```

**Error: "Vehicle already exists"**
- This is normal if vehicles were already imported
- The script will skip duplicates

### Frontend Not Loading

**Error: "Failed to fetch" or API connection issues**
1. Ensure backend is running: `docker compose up` or `./scripts/dev-local.sh`
2. Check API is accessible: `curl http://localhost:18080/docs`
3. Verify API base URL in browser console

### Vehicles Not Showing

1. Check if vehicles were imported successfully (check script output)
2. Verify you're logged in to the correct operator (`eleride-fleet`)
3. Refresh the vehicles list (click "Refresh vehicles" button)

## Local Development Notes

⚠️ **Important**: 
- This is for **LOCAL DEVELOPMENT ONLY**
- **DO NOT** push changes to AWS/Terraform until development is complete
- All changes are tested on localhost first
- Database changes are local (Docker Postgres)

## Next Steps

After importing and testing locally:
1. ✅ Verify all vehicles imported correctly
2. ✅ Check vehicle details show all registration information
3. ✅ Verify VIN is displayed correctly in list view
4. ✅ Test location display (update telemetry to see arena changes)
5. ✅ Verify dashboard shows correct vehicle count

Once everything works locally, you can deploy to AWS using the deployment scripts.

