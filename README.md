# FirstStep Supabase Competitor Intelligence

This is a **new** staff-only Supabase-backed Flask website. It is **separate** from the original MySQL website and the Inventory/Business Analytics Supabase project.

## Setup on Windows

1. Supabase project `ScrapWebsite` (`hvziaygxgnncjsxskjij`) has already received the three `fs_competitor_*` tables with RLS enabled and no direct anon/authenticated grants. Keep `schema.sql` as a reference; **do not run it again unless rebuilding another project**.
2. Copy `.env.example` to `.env` and set the **publishable key**, **server-side service-role/secret key** (never in frontend/GitHub), `ALLOWED_EMAILS`, and a random `FLASK_SECRET_KEY` (32+ characters). Get keys from Supabase Dashboard → Project Settings → API Keys.
3. In Supabase Dashboard → Authentication → Users, create/invite and verify the email in `ALLOWED_EMAILS`. Login requires a real Supabase password.
4. Double-click `START_FIRSTSTEP.bat`; open http://127.0.0.1:5050/login. Close the old Flask instance before running.
5. To enable paid scraping, add your `APIFY_TOKEN` to private `.env`, check provider pricing and caps, then use Scraping Control. Without the token, scraping is disabled; browsing and manual reviews still work.

## Data and safety

- Newly created Supabase tables are initially empty. Existing MySQL competitor listings are **not** automatically migrated. Your prior product count and price history will not appear until imported separately.
- App uses server-side service-role credentials and explicitly checks verified Supabase Auth users against `ALLOWED_EMAILS` before accessing data. Never deploy publicly with the Flask development server.
- All new provider matches remain `REVIEW`. A matching keyword does not guarantee the exact variant; confirm product pages and price before approval. The same Shopee URL may no longer represent a live offer; no real-time listing status is implied.
- Scraping is billable; actor caps may not encompass all Apify charges. A local single-process lock/cooldown is provided, **not a multi-worker distributed queue**. Do not run multiple app instances for collection.
- Our known Shop ID `994773440` is excluded. The Shop Directory includes IDs from the product URLs. Listing URL matching handles `&#x27;` HTML entities.
- The UI is a first operational version focused on product tracking and reviews; sales/profit dashboards are separate and not migrated into this project.
