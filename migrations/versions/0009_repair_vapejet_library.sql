-- Idempotent repair for deployments where the 0007 Vape-Jet seed was absent.
insert into public.coman_machine_models (
    id, manufacturer, model, category, operations_json,
    published_max_rate, rate_unit, published_min_operators,
    published_max_operators, planning_utilization_pct, source_url,
    source_checked_at, active, created_at, updated_at
) values
('46ea9f9f-e075-4dc4-b80d-a46769440012','Vape-Jet','Vape-Jet 4.0','automatic vape cartridge and device filling','["oil heating","machine-vision alignment","precision filling","run data capture"]',1200,'devices/hour',1,1,70,'https://vape-jet.com/faq/','2026-07-20T00:00:00Z',true,'2026-07-20T00:00:00Z','2026-07-20T00:00:00Z'),
('46ea9f9f-e075-4dc4-b80d-a46769440013','Vape-Jet','Jet Fueler 3.0','semi-automatic vape cartridge and device filling','["oil heating","foot-pedal dispensing","precision filling"]',1125,'devices/hour',1,1,65,'https://vape-jet.com/category/events/','2026-07-20T00:00:00Z',true,'2026-07-20T00:00:00Z','2026-07-20T00:00:00Z')
on conflict (manufacturer, model) do update set
category=excluded.category, operations_json=excluded.operations_json,
published_max_rate=excluded.published_max_rate, rate_unit=excluded.rate_unit,
published_min_operators=excluded.published_min_operators,
published_max_operators=excluded.published_max_operators,
planning_utilization_pct=excluded.planning_utilization_pct,
source_url=excluded.source_url, source_checked_at=excluded.source_checked_at,
active=true, updated_at=excluded.updated_at;

