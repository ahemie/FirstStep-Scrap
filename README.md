# FirstStep Shopee Competitor Intelligence — Supabase / FirstWell + Probiotickids

One complete Flask website. This edition checks two supplied Shopee Mass Update files to recognize FirstStep's own product Item IDs, and shows up to 10 actual matched results from each paid Apify search.

## Our owned Shopee shops

| Excel source | Shop ID | Unique Product / Item IDs |
|---|---|---:|
| FirstWell | 1688602696 | 243 |
| Probiotickids | 994773440 | 490 |

The IDs come from `mass_update_sales_info_FirstWell.xlsx` and `mass_update_sales_info_Probiotickids.xlsx`. In these reports, **Product ID is Shopee Item ID**, and `D2` contains the Shop ID. Variations sharing a Product ID count as one item. The project includes `data/own_catalog.json` with all 733 distinct records; the two XLSX files themselves are not required to run.

## Install on Windows

1. Extract the ZIP to `FirstStep_Supabase_Scraper` (keep old folder as backup).
2. Preserve your private `.env` file from your current running project, or make a **new** `.env` by copying `.env.example`. Never commit or send `.env`.
3. Ensure `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `ALLOWED_EMAILS`, and `FLASK_SECRET_KEY` are configured in `.env`. The Supabase project is **ScrapWebsite**.
4. Database tables were updated in the linked Supabase ScrapWebsite project. If using a different Supabase project, run `schema.sql` first in its SQL editor (or `schema_upgrade.sql` if the previous three tables already exist).
5. Double-click `START_FIRSTSTEP.bat`; sign in at http://127.0.0.1:5050/login using a verified allowlisted Supabase staff account.
6. Open **Our Product IDs**. The built-in list already works; optionally click **Sync both built-in Excel catalogs** to store the 733 IDs in Supabase. You may upload newer FirstWell/Probiotickids Shopee Mass Update XLSX reports later. Import validates the shop ID and does not delete other data.
7. Open **Manage Products** and use the new **Search FirstWell & Probiotickids Excel products** box. Choose **Use product** to pre-fill the product form, then check the pack and save. The product table shows all matching FirstWell/Probiotickids Shop IDs and Item IDs as catalog suggestions. Add/search an exact product name (e.g. `ORAC KIDS IMMUNE BOOSTER 5GMx6`) and expected pack (`5g x 6`).
8. Open **Scraping Control**; select the product. The **Known own products in Excel** section displays matches from the files *without* using Apify or claiming they were scraped.
9. For real Shopee results, provide your private `APIFY_TOKEN`, confirm potential charges and click **Start Live Scrape**. The **Top 10** section displays only real provider listings matching exact keywords and pack, including our own shop results when returned. Fewer than 10 is expected when fewer qualify.
10. In **Competitor Listings**, click the real Shopee link and verify current product / size / variation / price before selecting APPROVE for another seller. Our own shops cannot be approved as competitors.

**Apify cost:** Live calls are billable and require account credits. Default requests at most 30 provider candidates to find up to 10 relevant listings, with `MAX_CHARGE_PER_RUN_USD=0.25`. Provider pricing and quota may restrict the result, or cause the call to fail. No data is fabricated or silently substituted from Excel.

**Data behavior:** `fs_competitor_listings` preserves prior review decisions and stored prices when encountering the same URL/date; new scrape jobs reference existing rows where applicable. The job-results page shows only records returned by that job. The two shop IDs are recognized even if a product is not in the XLSX catalog. A separate panel shows Excel reference matches, which are **not** live listings. Multiple variation rows in Excel become one item.

**Security:** Staff-only Supabase Auth, allowlisted email and CSRF, server-only Supabase secret and Apify token. Supabase competitor tables have RLS and no direct browser access. Never push `.env` to GitHub. `.env.example` must only contain placeholders. Local Flask development server is not designed for public deployment.

**Testing:** Run `python -m unittest discover -s tests`. A paid Apify run and real login require your local credentials; neither is executed by the offline unit tests.

## This upgrade

- Manage Products now supports catalog search and prefilling from either Excel source, no Apify credit required.
- Each tracked product shows multiple own-shop catalog listings where the **name and pack** match; these are suggested associations rather than verified live Shopee listings.
- Existing tracked product columns and Supabase schema are unchanged; no migration required for this UI upgrade.
- Fixed the Apify Actor `Run` object error for status and dataset ID access.

## Best-selling search update

- Apify keyword searches request `sort: sales` for Shopee Malaysia (`country: my`). This is Shopee's sales-ranked search order, **not** a verified ranking of shops by total sales.
- Only exact-name/pack-matched candidates appear, up to 10; fewer are normal. Provider ordering and missing sold-count fields may prevent independently validating the sales rank.
- Missing seller names no longer display 'Seller not provided'; Shop ID and ownership badge remain visible.
