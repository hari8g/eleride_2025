-- Delete old vehicles matching pattern MH12LZ
-- This script deletes vehicles with registration numbers like MH12LZ*

-- First, show what will be deleted
SELECT 
    v.id, 
    v.registration_number, 
    v.operator_id,
    (SELECT COUNT(*) FROM vehicle_telemetry_events WHERE vehicle_id = v.id) as telemetry_count,
    (SELECT COUNT(*) FROM telematics_devices WHERE vehicle_id = v.id) as device_count,
    (SELECT COUNT(*) FROM maintenance_records WHERE vehicle_id = v.id) as maintenance_count
FROM vehicles v
WHERE v.registration_number LIKE '%MH12LZ%';

-- Delete related records first
DELETE FROM vehicle_telemetry_events 
WHERE vehicle_id IN (SELECT id FROM vehicles WHERE registration_number LIKE '%MH12LZ%');

DELETE FROM telematics_devices 
WHERE vehicle_id IN (SELECT id FROM vehicles WHERE registration_number LIKE '%MH12LZ%');

DELETE FROM maintenance_records 
WHERE vehicle_id IN (SELECT id FROM vehicles WHERE registration_number LIKE '%MH12LZ%');

-- Finally, delete the vehicles
DELETE FROM vehicles 
WHERE registration_number LIKE '%MH12LZ%';

-- Show remaining count
SELECT COUNT(*) as remaining_vehicles FROM vehicles;

