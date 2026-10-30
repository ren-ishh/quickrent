-- Explicit fleet categories for customer discovery and vehicle management.
alter table public.vehicles
  add column if not exists tier text not null default 'regular',
  add column if not exists body_style text;

update public.vehicles
set body_style = case
  when type = 'bike' then 'motorcycle'
  when type = 'scooter' then 'scooter'
  when type = 'car' and coalesce(name, '') ~* '(suv|fortuner|innova|scorpio|thar|creta|seltos|harrier|safari|xuv|brezza|nexon|elevate|alcazar)' then 'suv'
  when type = 'car' and coalesce(name, '') ~* '(hatchback|swift|i10|i20|baleno|polo|tiago|altroz)' then 'hatchback'
  when type = 'car' then 'sedan'
  else 'scooter'
end
where body_style is null;

alter table public.vehicles
  alter column body_style set default 'sedan';
