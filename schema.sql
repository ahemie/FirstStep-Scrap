-- FirstStep competitor intelligence; isolated from Inventory/Clinic tables.
create table if not exists public.fs_competitor_products (
 id bigint generated always as identity primary key,
 name text not null, keyword text not null, our_price numeric(12,2),
 own_shop_id text, own_item_id text, expected_pack text,
 active boolean not null default true, created_at timestamptz not null default now()
);
create table if not exists public.fs_competitor_listings (
 id bigint generated always as identity primary key,
 product_id bigint not null references public.fs_competitor_products(id) on delete restrict,
 shop_id text, item_id text, seller_name text, title text not null,
 url text not null, price numeric(12,2) not null check (price >= 0),
 rating numeric, sold_display text, snapshot_date date not null default current_date,
 status text not null default 'REVIEW' check(status in ('REVIEW','APPROVE','EXCLUDE','UNAVAILABLE')),
 match_hint text, verified_by uuid, reviewed_at timestamptz,
 collected_at timestamptz not null default now(),
 unique(product_id,url,snapshot_date)
);
create index if not exists fs_competitor_listings_product_idx on public.fs_competitor_listings(product_id,snapshot_date desc);
create table if not exists public.fs_competitor_jobs (
 id bigint generated always as identity primary key,
 product_id bigint not null references public.fs_competitor_products(id),
 status text not null check(status in ('STARTED','COMPLETED','FAILED')),
 requested_by uuid, started_at timestamptz not null default now(),
 finished_at timestamptz, candidate_count int not null default 0,
 saved_count int not null default 0, message text
);
-- No browser-direct access. Flask uses a secret key only on the server.
alter table public.fs_competitor_products enable row level security;
alter table public.fs_competitor_listings enable row level security;
alter table public.fs_competitor_jobs enable row level security;
revoke all on public.fs_competitor_products,public.fs_competitor_listings,public.fs_competitor_jobs from anon,authenticated;
revoke all on sequence public.fs_competitor_products_id_seq,public.fs_competitor_listings_id_seq,public.fs_competitor_jobs_id_seq from anon,authenticated;
