-- Safe, additive FirstStep Supabase scraping upgrade (October 2026).
-- Apply only to the FirstStep ScrapWebsite Supabase project.
-- No historical competitor or job data is deleted.
create table if not exists public.fs_competitor_own_catalog (
  source text not null check (source in ('FirstWell','Probiotickids')),
  shop_id text not null,
  item_id text not null,
  title text not null,
  variation_count integer not null default 1 check(variation_count > 0),
  imported_at timestamptz not null default now(),
  primary key(shop_id,item_id)
);
alter table public.fs_competitor_listings
  add column if not exists last_job_id bigint references public.fs_competitor_jobs(id) on delete set null;
alter table public.fs_competitor_listings
  add column if not exists result_rank integer;
create index if not exists fs_competitor_listings_job_rank_idx
  on public.fs_competitor_listings(last_job_id,result_rank);
alter table public.fs_competitor_own_catalog enable row level security;
revoke all on table public.fs_competitor_own_catalog from anon,authenticated;
-- Only the authenticated Flask backend uses the service-role client to access these tables.
