"""
FirstStep Supabase Competitor Intelligence — staff-only Shopee MY collection.
The uploaded FirstWell and Probiotickids item IDs are always considered our shop.
No paid collection happens without a logged-in staff user's explicit confirmation.
"""
from __future__ import annotations
from datetime import datetime, timezone

import datetime as dt
import html
import os
import re
import secrets
import threading
import time
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session
from supabase import create_client

from matching import match_detail
from catalog_search import search_catalog, catalog_for_product
from own_catalog import SOURCES, bundled_catalog, classify, read_xlsx_catalog

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', '')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  MAX_CONTENT_LENGTH=10 * 1024 * 1024)
SCRAPE_LOCK = threading.Lock()
CACHE_LOCK = threading.Lock()
CATALOG_CACHE = {'until': 0.0, 'rows': []}
OWN_SHOPS = {x.strip() for x in os.getenv('OWN_SHOP_IDS', '994773440,1688602696').split(',') if x.strip()} | set(SOURCES.values())


def config_ok():
    return bool(os.getenv('SUPABASE_URL', '').startswith('https://') and
                os.getenv('SUPABASE_PUBLISHABLE_KEY') and os.getenv('SUPABASE_SERVICE_ROLE_KEY') and
                len(os.getenv('FLASK_SECRET_KEY', '')) >= 32 and os.getenv('ALLOWED_EMAILS'))


def db():
    return create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])


def staff():
    allowed = {s.strip().lower() for s in os.getenv('ALLOWED_EMAILS', '').split(',') if s.strip()}
    return bool(session.get('user_id') and session.get('email') in allowed)


def protected(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not staff():
            return jsonify(error='Sign in required'), 401
        if request.method not in ('GET', 'HEAD') and request.headers.get('X-CSRF-Token') != session.get('csrf'):
            return jsonify(error='Security token invalid. Refresh and sign in again.'), 403
        return fn(*args, **kwargs)
    return wrapped


@app.after_request
def response_headers(resp):
    resp.headers['Cache-Control'] = 'no-store'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Content-Security-Policy'] = ("default-src 'self'; script-src 'self'; style-src 'self'; "
                                               "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
    return resp


@app.get('/login')
def login():
    return render_template('login.html', error=None, configured=config_ok())


@app.post('/login')
def login_post():
    email = (request.form.get('email') or '').strip().lower()
    password = request.form.get('password') or ''
    allowed = {s.strip().lower() for s in os.getenv('ALLOWED_EMAILS', '').split(',')}
    if not config_ok() or email not in allowed or len(password) > 1000:
        return render_template('login.html', error='Login failed or staff email is not allowed', configured=config_ok()), 403
    try:
        auth = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_PUBLISHABLE_KEY'])
        result = auth.auth.sign_in_with_password({'email': email, 'password': password})
        user = auth.auth.get_user(result.session.access_token).user
        if not user or not user.email or user.email.lower() != email or not user.email_confirmed_at:
            raise ValueError('Email not verified')
        session.clear()
        session.update(user_id=str(user.id), email=email, csrf=secrets.token_urlsafe(24))
        return redirect('/')
    except Exception:
        return render_template('login.html', error='Login failed. Check Supabase staff credentials and verified email.', configured=True), 403


@app.post('/logout')
@protected
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get('/')
def home():
    return render_template('index.html') if staff() else redirect('/login')


@app.get('/api/session')
@protected
def api_session():
    return jsonify(email=session['email'], csrf=session['csrf'])


def parsed_ids(url):
    """Extract untrusted Shopee URL IDs only from genuine Malaysia HTTPS hosts."""
    if not isinstance(url, str):
        return None, None
    try:
        u = urlsplit(html.unescape(url.strip()))
        if u.scheme != 'https' or u.hostname not in ('shopee.com.my', 'www.shopee.com.my') or u.username or u.password or u.port is not None:
            return None, None
        path = unquote(u.path)
        m = re.search(r'-i\.(\d+)\.(\d+)/?$', path, re.I) or re.fullmatch(r'/product/(\d+)/(\d+)/?', path, re.I)
        return (m.group(1), m.group(2)) if m else (None, None)
    except (ValueError, TypeError):
        return None, None


def products():
    return db().table('fs_competitor_products').select('*').order('id').execute().data or []


def catalog_rows():
    """Overlay staff-updated Supabase catalog on bundled Excel reference IDs."""
    now = time.monotonic()
    with CACHE_LOCK:
        if now < CATALOG_CACHE['until']:
            return CATALOG_CACHE['rows']
    merged = {(str(row['shop_id']), str(row['item_id'])): row for row in bundled_catalog()}
    start = 0
    while True:
        page = (db().table('fs_competitor_own_catalog')
                .select('source,shop_id,item_id,title,variation_count')
                .order('item_id').range(start, start+499).execute().data or [])
        for row in page:
            merged[(str(row['shop_id']), str(row['item_id']))] = row
        if len(page) < 500:
            break
        start += 500
    rows = list(merged.values())
    with CACHE_LOCK:
        CATALOG_CACHE.update(rows=rows, until=time.monotonic()+90)
    return rows


def invalidate_catalog():
    with CACHE_LOCK:
        CATALOG_CACHE['until'] = 0


def owned(shop_id, item_id, reference=None, product_list=None):
    rows = catalog_rows() if reference is None else reference
    known = set(OWN_SHOPS)
    for p in (products() if product_list is None else product_list):
        if p.get('own_shop_id'):
            known.add(str(p['own_shop_id']))
    return classify(shop_id, item_id, rows, known)


def annotate(row, reference=None, product_list=None):
    result = dict(row)
    result.update(owned(row.get('shop_id'), row.get('item_id'), reference, product_list))
    return result


@app.get('/api/products')
@protected
def list_products():
    return jsonify(products=products())


@app.post('/api/products')
@protected
def add_product():
    data = request.get_json(silent=True) or {}
    name = ' '.join(str(data.get('name') or '').split())[:255]
    keyword = ' '.join(str(data.get('keyword') or name).split())[:255]
    if len(name) < 3 or not keyword:
        return jsonify(error='Enter product name and search keywords'), 400
    row = {'name': name, 'keyword': keyword, 'expected_pack': str(data.get('pack') or '')[:120]}
    if data.get('our_price') not in (None, ''):
        try:
            price = Decimal(str(data['our_price']))
            if not price.is_finite() or price <= 0 or price > 99999999:
                raise ValueError()
            row['our_price'] = float(price)
        except (InvalidOperation, ValueError):
            return jsonify(error='Invalid product price'), 400
    if data.get('own_url'):
        shop, item = parsed_ids(data['own_url'])
        if not shop:
            return jsonify(error='Use a valid Shopee Malaysia product URL'), 400
        row.update(own_shop_id=shop, own_item_id=item)
    return jsonify(product=db().table('fs_competitor_products').insert(row).execute().data[0]), 201


@app.patch('/api/products/<int:product_id>')
@protected
def edit_product(product_id):
    data = request.get_json(silent=True) or {}
    row = {}
    for key in ('name', 'keyword', 'expected_pack'):
        if key in data:
            row[key] = ' '.join(str(data[key]).split())[:255]
    if 'active' in data:
        row['active'] = data['active'] is True
    if 'our_price' in data:
        try:
            if data['our_price'] in ('', None):
                row['our_price'] = None
            else:
                value = Decimal(str(data['our_price']))
                if not value.is_finite() or value <= 0 or value > 99999999 or value.as_tuple().exponent < -2:
                    raise ValueError()
                row['our_price'] = float(value)
        except (InvalidOperation, ValueError):
            return jsonify(error='Invalid product price'), 400
    if 'own_url' in data:
        shop, item = parsed_ids(data['own_url'])
        if not shop:
            return jsonify(error='Invalid Shopee URL'), 400
        row.update(own_shop_id=shop, own_item_id=item)
    if not row:
        return jsonify(error='No fields to update'), 400
    return jsonify(rows=db().table('fs_competitor_products').update(row).eq('id',product_id).execute().data)


@app.post('/api/products/<int:product_id>/archive')
@protected
def archive_product(product_id):
    """Hide a product from active tracking without destroying price history."""
    data = request.get_json(silent=True) or {}
    if data.get('confirm') is not True:
        return jsonify(error='Confirm removal before archiving this product'), 400
    existing = (db().table('fs_competitor_products').select('id,active')
                .eq('id', product_id).limit(1).execute().data or [])
    if not existing:
        return jsonify(error='Tracked product not found'), 404
    if not existing[0]['active']:
        return jsonify(ok=True, already_archived=True)
    db().table('fs_competitor_products').update({'active': False}).eq('id', product_id).execute()
    return jsonify(ok=True, archived_id=product_id, message='Product removed from tracking. Historical prices preserved.')


@app.get('/api/catalog')
@protected
def get_catalog():
    rows = catalog_rows()
    counts = {key:sum(r['source']==key for r in rows) for key in SOURCES}
    return jsonify(counts=counts, total=len(rows), shops=SOURCES,
                   note='Product ID in the Excel is the Shopee Item ID. Variation IDs are not shop IDs.')


@app.get('/api/catalog/search')
@protected
def search_own_catalog():
    query = request.args.get('q', '').strip()
    if len(query) > 200:
        return jsonify(error='Search is too long'), 400
    rows = search_catalog(catalog_rows(), query)
    return jsonify(results=rows, count=len(rows),
                   note='Catalog entries are from the FirstWell and Probiotickids Excel files, not live Shopee results.')


@app.get('/api/products/catalog-links')
@protected
def product_catalog_links():
    reference = catalog_rows()
    return jsonify(links={str(p['id']):catalog_for_product(reference,p) for p in products()},
                   note='Suggested links from exact product title and pack; confirm variations before relying on them.')


@app.get('/api/catalog/matches')
@protected
def catalog_matches():
    try:
        pid = int(request.args.get('product_id', ''))
    except ValueError:
        return jsonify(error='Select a product'), 400
    p = next((p for p in products() if p['id']==pid), None)
    if not p:
        return jsonify(error='Product not found'),404
    selected = catalog_for_product(catalog_rows(), p)
    selected.sort(key=lambda r:(r['source'],r['title']))
    return jsonify(matches=selected[:30], total=len(selected),
                   note='These IDs come from your uploaded Excel reference, NOT a live Shopee scrape.')


def upload_catalog_rows(rows):
    for i in range(0, len(rows), 100):
        db().table('fs_competitor_own_catalog').upsert(rows[i:i+100], on_conflict='shop_id,item_id').execute()
    invalidate_catalog()


@app.post('/api/catalog/sync')
@protected
def sync_bundled_catalog():
    rows = bundled_catalog()
    if not rows:
        return jsonify(error='No bundled Excel references found'), 400
    upload_catalog_rows(rows)
    return jsonify(ok=True, synced=len(rows), message='Excel product IDs synced to Supabase')


@app.post('/api/catalog/upload/<source>')
@protected
def upload_catalog(source):
    file = request.files.get('file')
    if not file or not file.filename or not file.filename.lower().endswith('.xlsx'):
        return jsonify(error='Choose a Shopee Mass Update XLSX file'),400
    try:
        rows = read_xlsx_catalog(file.read(), source)
    except (ValueError, KeyError, OSError) as exc:
        return jsonify(error=str(exc)),400
    upload_catalog_rows(rows)
    return jsonify(ok=True, source=source, imported=len(rows))


@app.get('/api/listings')
@protected
def listings():
    query = db().table('fs_competitor_listings').select('*').order('collected_at', desc=True).limit(1000)
    if request.args.get('product_id'):
        try:
            query = query.eq('product_id', int(request.args['product_id']))
        except ValueError:
            return jsonify(error='Invalid product filter'),400
    rows = query.execute().data or []
    ref, ps = catalog_rows(), products()
    for i,row in enumerate(rows):
        rows[i] = annotate(row, ref, ps)
    return jsonify(listings=rows)


def build_price_overview(ps, rows, ref):
    """Summarize ONLY matching, manually approved, non-owned listings.

    Latest price statistics use the newest approved date for each product.
    Older snapshots are included in the historical trend, never as current prices.
    """
    result = []
    approved_total = 0
    from datetime import date as _date
    today = _date.today()
    for p in ps:
        if not p.get('active', True):
            continue
        eligible = [r for r in rows if r.get('product_id') == p['id']
                    and r.get('status') == 'APPROVE'
                    and not owned(r.get('shop_id'),r.get('item_id'),ref,ps)['own_shop']
                    and match_detail(r.get('title') or '',p['keyword'],p.get('expected_pack') or '')[0]
                    and r.get('snapshot_date') and r.get('price') is not None]
        approved_total += len(eligible)
        latest = max((str(r['snapshot_date']) for r in eligible),default=None)
        current = [float(r['price']) for r in eligible if str(r['snapshot_date'])==latest]
        own_price = float(p['our_price']) if p.get('our_price') is not None else None
        lowest = min(current) if current else None
        average = round(sum(current)/len(current),2) if current else None
        highest = max(current) if current else None
        gap = round(own_price - lowest,2) if own_price is not None and lowest is not None else None
        gap_pct = round(100*gap/lowest,2) if gap is not None and lowest else None
        by_date = {}
        for r in eligible:
            date = str(r['snapshot_date'])
            by_date.setdefault(date,[]).append(float(r['price']))
        history = [{'date':date,'lowest':min(values),
                    'average':round(sum(values)/len(values),2),
                    'highest':max(values),'count':len(values)}
                   for date,values in sorted(by_date.items())]
        age_days = (today - _date.fromisoformat(latest)).days if latest else None
        if gap is None:
            action = 'ADD_OUR_PRICE' if own_price is None else 'REVIEW_COMPETITORS'
        elif age_days is not None and age_days > 30:
            action = 'REFRESH_SNAPSHOT'
        elif gap > 0:
            action = 'PRICE_RISK'
        elif gap < 0:
            action = 'PRICE_ADVANTAGE'
        else:
            action = 'AT_PAR'
        result.append({'product':p,'approved':len(eligible),'current_count':len(current),
                       'age_days':age_days,'action':action,
                       'snapshot_date':latest,'lowest':lowest,'average':average,'highest':highest,
                       'gap_rm':gap,'gap_percent':gap_pct,'history':history})
    compared = [r for r in result if r['gap_rm'] is not None]
    return {'products':result,'total_listings':len(rows),'approved':approved_total,
            'pending':sum(r.get('status')=='REVIEW' for r in rows),
            'products_compared':len(compared),
            'priced_above_lowest':sum(r['gap_rm']>0 for r in compared),
            'priced_below_lowest':sum(r['gap_rm']<0 for r in compared),
            'missing_comparison':len(result)-len(compared),
            'stale_products':sum(r['age_days'] is not None and r['age_days']>30 for r in result),
            'as_of':today.isoformat(),
            'average_gap_rm':round(sum(r['gap_rm'] for r in compared)/len(compared),2) if compared else None,
            'note':'Approved matching competitor snapshots only; historical prices are not live offers.'}


@app.get('/api/overview')
@protected
def overview():
    ps=products()
    ref=catalog_rows()
    # Supabase paginates larger result sets. Page through every record to avoid
    # inaccurate summary metrics when more than 1,000 rows exist.
    rows=[]
    for offset in range(0,100000,1000):
        batch=(db().table('fs_competitor_listings')
               .select('product_id,price,status,shop_id,item_id,snapshot_date,title')
               .order('id').range(offset,offset+999).execute().data or [])
        rows.extend(batch)
        if len(batch)<1000:
            break
    return jsonify(build_price_overview(ps,rows,ref))


@app.post('/api/listings/<int:listing_id>/decision')
@protected
def decision(listing_id):
    data = request.get_json(silent=True) or {}
    status = str(data.get('status','')).upper()
    if status not in {'APPROVE','REVIEW','EXCLUDE','UNAVAILABLE'}:
        return jsonify(error='Invalid review decision'),400
    result=db().table('fs_competitor_listings').select('*').eq('id',listing_id).limit(1).execute().data
    if not result:
        return jsonify(error='Listing not found'),404
    row=result[0]
    classification=owned(row.get('shop_id'),row.get('item_id'))
    if status=='APPROVE':
        if data.get('verified') is not True:
            return jsonify(error='Confirm exact product, pack, variation and price before approving'),400
        if not row.get('shop_id') or classification['own_shop'] or classification['own_match']=='ID_CONFLICT':
            return jsonify(error='Cannot approve our shop or unidentified/conflicting Shop ID'),400
        p=next((x for x in products() if x['id']==row['product_id']),None)
        if not p or not match_detail(row['title'],p['keyword'],p.get('expected_pack') or '')[0]:
            return jsonify(error='Product name or pack does not match; leave as REVIEW or EXCLUDE'),400
    payload={'status':status,'verified_by':session['user_id'],
             'reviewed_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    saved=db().table('fs_competitor_listings').update(payload).eq('id',listing_id).execute().data
    return jsonify(row=annotate(saved[0]))


@app.get('/api/jobs')
@protected
def jobs():
    return jsonify(jobs=db().table('fs_competitor_jobs').select('*').order('started_at',desc=True).limit(30).execute().data)


@app.get('/api/jobs/<int:job_id>/results')
@protected
def job_results(job_id):
    jobs=db().table('fs_competitor_jobs').select('*').eq('id',job_id).limit(1).execute().data
    if not jobs:
        return jsonify(error='Scraping job not found'),404
    rows=(db().table('fs_competitor_listings').select('*').eq('last_job_id',job_id)
          .order('result_rank').limit(10).execute().data or [])
    ref, ps=catalog_rows(),products()
    return jsonify(job=jobs[0],listings=[annotate(r,ref,ps) for r in rows])


def _price(value):
    if isinstance(value,dict):
        value=value.get('value') or value.get('price')
    cleaned=re.sub(r'(?i)rm\s*|,|\s+', '',str(value or ''))
    try:
        price=Decimal(cleaned)
        return price if price.is_finite() and 0<price<=99999999 else None
    except InvalidOperation:
        return None


def _save_scraped_item(item, product, job_id, rank, ref, ps):
    title=item.get('name') or item.get('title') or item.get('product_name') or ''
    url=item.get('url') or item.get('product_url') or item.get('link') or ''
    shop, item_id=parsed_ids(url)
    good,reason=match_detail(title,product['keyword'],product.get('expected_pack') or '')
    price=_price(item.get('price'))
    if not good or not shop or not item_id or price is None:
        return False
    classification=owned(shop,item_id,ref,ps)
    raw_seller=item.get('shop_name') or item.get('seller_name') or item.get('seller')
    if isinstance(raw_seller,dict):
        raw_seller=raw_seller.get('name')
    if not raw_seller and isinstance(item.get('shop'),dict):
        raw_seller=item['shop'].get('name')
    date=datetime.now(timezone.utc).date().isoformat()
    existing=(db().table('fs_competitor_listings').select('id').eq('product_id',product['id'])
              .eq('url',url[:500]).eq('snapshot_date',date).limit(1).execute().data or [])
    if existing:
        # Preserve staff decisions and historical prices; link this existing row to the new job.
        db().table('fs_competitor_listings').update({'last_job_id':job_id,'result_rank':rank}).eq('id',existing[0]['id']).execute()
    else:
        row={'product_id':product['id'],'shop_id':shop,'item_id':item_id,
             'seller_name':str(raw_seller)[:255] if raw_seller else None,
             'title':str(title)[:2000], 'url':str(url)[:500], 'price':float(price),
             'status':'EXCLUDE' if classification['own_shop'] else 'REVIEW',
             'match_hint':reason, 'snapshot_date':date, 'last_job_id':job_id,
             'result_rank':rank}
        db().table('fs_competitor_listings').insert(row).execute()
    return True


def collect_worker(product, job_id):
    saved=0
    scanned=0
    status='FAILED'
    message=''
    try:
        from apify_client import ApifyClient
        token=os.environ['APIFY_TOKEN']
        limit=max(1,min(int(os.getenv('MAX_RESULTS_PER_PRODUCT','10')),10))
        pool=max(limit,min(int(os.getenv('SEARCH_CANDIDATES_PER_RUN','30')),50))
        cap=float(os.getenv('MAX_CHARGE_PER_RUN_USD','0.25'))
        client=ApifyClient(token)
        result=client.actor(os.getenv('APIFY_ACTOR_ID','xtracto/shopee-search')).call(
            run_input={'country':'my','mode':'keyword','keyword':product['keyword'],
                       'sort':'sales','maxProducts':pool,'fetchDetail':False},
            max_items=pool,max_total_charge_usd=cap)
        run_status = (result.get('status') if isinstance(result, dict) else getattr(result, 'status', None)) if result else None
        if getattr(run_status, 'value', run_status) != 'SUCCEEDED':
            raise RuntimeError('Apify Actor did not complete successfully')
        dataset_id = (result.get('defaultDatasetId') if isinstance(result, dict) else getattr(result, 'default_dataset_id', None))
        if not dataset_id:
            raise RuntimeError('Apify run returned no dataset ID')
        raw=client.dataset(dataset_id).list_items(limit=pool).items
        ref, ps=catalog_rows(), products()
        for item in raw:
            scanned+=1
            if saved>=limit:
                break
            if not isinstance(item,dict):
                continue
            if _save_scraped_item(item,product,job_id,saved+1,ref,ps):
                saved+=1
        status='COMPLETED'
        message=(f'Scanned {scanned} Shopee search results; found {saved} matching listings. '
                 'Requested Shopee best-selling order (sales); matching product and pack filters still apply. Our shops are included and labelled, not counted as competitors. '
                 'Fewer than 10 means fewer matching listings were returned.')
    except Exception as exc:
        message=f'{type(exc).__name__}: {str(exc)[:220]}'
    finally:
        try:
            db().table('fs_competitor_jobs').update({
                'status':status,'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                'candidate_count':scanned,'saved_count':saved,'message':message}).eq('id',job_id).execute()
        finally:
            SCRAPE_LOCK.release()


@app.post('/api/scrape')
@protected
def scrape():
    data=request.get_json(silent=True) or {}
    if data.get('confirm_paid') is not True:
        return jsonify(error='Confirm potentially paid Apify collection'),400
    if not os.getenv('APIFY_TOKEN'):
        return jsonify(error='Add APIFY_TOKEN to your private .env file'),400
    try:
        product_id=int(data.get('product_id'))
    except (TypeError,ValueError):
        return jsonify(error='Select a tracked product'),400
    p=next((x for x in products() if x['id']==product_id and x['active']),None)
    if not p:
        return jsonify(error='Product not found or inactive'),404
    previous=(db().table('fs_competitor_jobs').select('started_at').eq('product_id',product_id)
              .order('started_at',desc=True).limit(1).execute().data or [])
    if previous:
        when=dt.datetime.fromisoformat(previous[0]['started_at'].replace('Z','+00:00'))
        if (dt.datetime.now(dt.timezone.utc)-when).total_seconds()<300:
            return jsonify(error='Please wait 5 minutes before repeating this product scrape'),429
    if not SCRAPE_LOCK.acquire(False):
        return jsonify(error='Another scrape is already in progress'),409
    try:
        job=db().table('fs_competitor_jobs').insert({
            'product_id':product_id,'status':'STARTED','requested_by':session['user_id']}).execute().data[0]
        threading.Thread(target=collect_worker,args=(p,job['id']),daemon=True).start()
        return jsonify(job_id=job['id'],message='Paid scraping started. Results will appear under Top 10.'),202
    except Exception:
        SCRAPE_LOCK.release()
        raise


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify(error='Uploaded file is too large'),413


@app.errorhandler(Exception)
def on_error(error):
    app.logger.exception('FirstStep request failed')
    return jsonify(error='Server error; check your Flask terminal.'),500


if __name__=='__main__':
    if not config_ok():
        print('Configure .env using .env.example and sign in with a verified Supabase staff account')
        raise SystemExit(1)
    app.run(host='127.0.0.1',port=5050,debug=False)
