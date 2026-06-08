create extension if not exists pgcrypto;

create table if not exists public.incidents (
  id uuid primary key default gen_random_uuid(),
  service text not null,
  title text not null,
  status text not null,
  severity text not null,
  severity_class text,
  source text not null,
  alert_state text not null,
  occurrence_count integer not null default 1,
  owner_team text,
  alarm_name text,
  escalation_priority text,
  escalation_target text,
  runbook_url text,
  dashboard_url text,
  scenario_key text,
  summary text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.incident_steps (
  id uuid primary key default gen_random_uuid(),
  incident_id uuid not null references public.incidents(id) on delete cascade,
  phase text not null,
  description text not null,
  detail text,
  status text not null default 'completed',
  created_at timestamptz not null default now()
);

create table if not exists public.incident_reports (
  id uuid primary key default gen_random_uuid(),
  incident_id uuid not null references public.incidents(id) on delete cascade,
  report jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists incidents_created_at_idx on public.incidents (created_at desc);
create index if not exists incident_steps_incident_id_idx on public.incident_steps (incident_id);
create index if not exists incident_reports_incident_id_idx on public.incident_reports (incident_id);
