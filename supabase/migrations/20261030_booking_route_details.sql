-- Add route details for customer-created rentals. Existing bookings remain valid.
alter table public.bookings
  add column if not exists pickup_location text,
  add column if not exists dropoff_location text,
  add column if not exists pickup_latitude double precision,
  add column if not exists pickup_longitude double precision,
  add column if not exists dropoff_latitude double precision,
  add column if not exists dropoff_longitude double precision,
  add column if not exists distance_km numeric(10, 2),
  add column if not exists estimated_duration_minutes integer;

-- Optional real pickup coordinates power vehicle pins on the rental maps.
alter table public.vehicles
  add column if not exists latitude double precision,
  add column if not exists longitude double precision;
