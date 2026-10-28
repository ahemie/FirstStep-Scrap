"""FirstStep Supabase Shopee Competitor Intelligence (local, staff-only)."""
import os, re, html, secrets, threading, datetime as dt
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit
from functools import wraps
from flask import Flask, request, jsonify, redirect, render_template, session
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).with_name('.env'))
app=Flask(__name__)
app.secret_key=os.getenv('FLASK_SECRET_KEY','')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',MAX_CONTENT_LENGTH=256000)
LOCK=threading.Lock()
OWN_SHOPS={x.strip() for x in os.getenv('OWN_SHOP_IDS','994773440').split(',') if x.strip()}
PROJECT='https://hvziaygxgnncjsxskjij.supabase.co'

def config_ok():
    return bool(os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_PUBLISHABLE_KEY') and os.getenv('SUPABASE_SERVICE_ROLE_KEY') and len(os.getenv('FLASK_SECRET_KEY',''))>=32 and os.getenv('ALLOWED_EMAILS'))

def db():
    return create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])

def staff():
    return bool(session.get('user_id') and session.get('email') in {s.strip().lower() for s in os.getenv('ALLOWED_EMAILS','').split(',')})

def protected(f):
    @wraps(f)
    def wrap(*args,**kwargs):
        if not staff():return jsonify(error='Sign in required'),401
        if request.method not in ('GET','HEAD') and request.headers.get('X-CSRF-Token')!=session.get('csrf'):
            return jsonify(error='Security token invalid'),403
        return f(*args,**kwargs)
    return wrap

@app.after_request
def headers(r):
    r.headers['Cache-Control']='no-store';r.headers['X-Content-Type-Options']='nosniff';r.headers['X-Frame-Options']='DENY'
    r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    return r

@app.get('/login')
def login():return render_template('login.html',error=None,configured=config_ok())

@app.post('/login')
def login_post():
    email=(request.form.get('email') or '').strip().lower();password=request.form.get('password') or ''
    if not config_ok() or email not in {s.strip().lower() for s in os.environ['ALLOWED_EMAILS'].split(',')}:
        return render_template('login.html',error='Login failed or staff email is not allowed',configured=config_ok()),403
    try:
        auth=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_PUBLISHABLE_KEY'])
        result=auth.auth.sign_in_with_password({'email':email,'password':password})
        user=auth.auth.get_user(result.session.access_token).user
        if not user or user.email.lower()!=email or not user.email_confirmed_at:raise ValueError('Unverified')
        session.clear();session.update(user_id=str(user.id),email=email,csrf=secrets.token_urlsafe(24))
        return redirect('/')
    except Exception:
        return render_template('login.html',error='Login failed. Check Supabase staff credentials and verified email.',configured=True),403

@app.post('/logout')
@protected
def logout():session.clear();return jsonify(ok=True)

@app.get('/')
def home():
    if not staff():return redirect('/login')
    return render_template('index.html')

@app.get('/api/session')
@protected
def api_session():return jsonify(email=session['email'],csrf=session['csrf'])

def parsed_ids(url):
    if not isinstance(url,str):return None,None
    try:
        u=urlsplit(html.unescape(url.strip()))
        if u.scheme!='https' or u.hostname not in ('shopee.com.my','www.shopee.com.my') or u.username or u.password or u.port is not None:return None,None
        p=u.path
        m=re.search(r'-i\.(\d+)\.(\d+)/?$',p,re.I) or re.fullmatch(r'/product/(\d+)/(\d+)/?',p,re.I)
        return (m.group(1),m.group(2)) if m else (None,None)
    except (ValueError,TypeError):return None,None

def words(s):return re.findall(r'[a-z0-9]+',html.unescape(s or '').lower())
def candidate_match(title,keyword):
    required=[w for w in words(keyword) if len(w)>1]
    found=words(title)
    return bool(required) and all(w in found for w in required)

def products():return db().table('fs_competitor_products').select('*').order('id').execute().data or []

@app.get('/api/products')
@protected
def list_products():return jsonify(products=products())

@app.post('/api/products')
@protected
def add_product():
    d=request.get_json(silent=True) or {};name=' '.join(str(d.get('name','')).split())[:255];keyword=' '.join(str(d.get('keyword') or name).split())[:255]
    if not name or len(name)<3 or not keyword:return jsonify(error='Enter a product name and keyword'),400
    payload={'name':name,'keyword':keyword,'expected_pack':str(d.get('pack') or '')[:120]}
    if d.get('our_price') not in (None,''):
        try:payload['our_price']=float(Decimal(str(d['our_price'])))
        except Exception:return jsonify(error='Invalid price'),400
    if d.get('own_url'):
        shop,item=parsed_ids(d['own_url'])
        if not shop:return jsonify(error='Enter a valid Shopee Malaysia product URL'),400
        payload.update(own_shop_id=shop,own_item_id=item)
    return jsonify(product=db().table('fs_competitor_products').insert(payload).execute().data[0]),201

@app.patch('/api/products/<int:product_id>')
@protected
def edit_product(product_id):
    d=request.get_json(silent=True) or {};p={}
    for key in ('name','keyword','expected_pack'):
        if key in d:p[key]=' '.join(str(d[key]).split())[:255]
    if 'active' in d:p['active']=d['active'] is True
    if 'our_price' in d:
        try:p['our_price']=float(Decimal(str(d['our_price']))) if d['our_price'] not in ('',None) else None
        except Exception:return jsonify(error='Invalid price'),400
    if 'own_url' in d:
        shop,item=parsed_ids(d['own_url']);
        if not shop:return jsonify(error='Invalid Shopee URL'),400
        p.update(own_shop_id=shop,own_item_id=item)
    return jsonify(rows=db().table('fs_competitor_products').update(p).eq('id',product_id).execute().data)

@app.get('/api/listings')
@protected
def listings():
    query=db().table('fs_competitor_listings').select('*').order('collected_at',desc=True).limit(1000)
    if request.args.get('product_id'):query=query.eq('product_id',int(request.args['product_id']))
    rows=query.execute().data or []
    own=OWN_SHOPS|{str(p['own_shop_id']) for p in products() if p.get('own_shop_id')}
    for row in rows:row['own_shop']=str(row.get('shop_id')) in own
    return jsonify(listings=rows)

@app.get('/api/overview')
@protected
def overview():
    ps=products();rows=db().table('fs_competitor_listings').select('product_id,price,status,shop_id,snapshot_date').limit(5000).execute().data or []
    out=[];own=OWN_SHOPS|{str(p['own_shop_id']) for p in ps if p.get('own_shop_id')}
    for p in ps:
        approved=[r for r in rows if r['product_id']==p['id'] and r['status']=='APPROVE' and str(r.get('shop_id')) not in own]
        latest=max((r['snapshot_date'] for r in approved),default=None)
        vals=[float(r['price']) for r in approved if r['snapshot_date']==latest]
        out.append({'product':p,'approved':len(approved),'snapshot_date':latest,'lowest':min(vals) if vals else None,'average':round(sum(vals)/len(vals),2) if vals else None,'highest':max(vals) if vals else None})
    return jsonify(products=out,total_listings=len(rows),pending=sum(r['status']=='REVIEW' for r in rows),approved=sum(r['status']=='APPROVE' for r in rows))

@app.post('/api/listings/<int:listing_id>/decision')
@protected
def decision(listing_id):
    d=request.get_json(silent=True) or {};status=d.get('status','').upper()
    if status not in ('APPROVE','REVIEW','EXCLUDE','UNAVAILABLE'):return jsonify(error='Invalid decision'),400
    result=db().table('fs_competitor_listings').select('*').eq('id',listing_id).limit(1).execute().data
    if not result:return jsonify(error='Listing not found'),404
    row=result[0]; own=OWN_SHOPS|{str(p['own_shop_id']) for p in products() if p.get('own_shop_id')}
    if status=='APPROVE':
        if not d.get('verified'):return jsonify(error='Confirm exact product, variation and price before approving'),400
        if not row.get('shop_id') or str(row['shop_id']) in own:return jsonify(error='Cannot approve own or unidentified shop'),400
        p=next((x for x in products() if x['id']==row['product_id']),None)
        if not p or not candidate_match(row['title'],p['keyword']):return jsonify(error='Title does not meet target keyword; set REVIEW'),400
    return jsonify(row=db().table('fs_competitor_listings').update({'status':status,'verified_by':session['user_id'],'reviewed_at':dt.datetime.now(dt.timezone.utc).isoformat()}).eq('id',listing_id).execute().data[0])

@app.get('/api/jobs')
@protected
def jobs():return jsonify(jobs=db().table('fs_competitor_jobs').select('*').order('started_at',desc=True).limit(30).execute().data)

def collect_worker(product,uid,jobid):
    from apify_client import ApifyClient
    n=0;considered=0;message=''
    try:
        token=os.environ['APIFY_TOKEN'];cap=float(os.getenv('MAX_CHARGE_PER_RUN_USD','0.25'));max_items=max(1,min(int(os.getenv('MAX_PRODUCTS_PER_SEARCH','10')),30))
        client=ApifyClient(token)
        result=client.actor(os.getenv('APIFY_ACTOR_ID','xtracto/shopee-search')).call(run_input={'country':'my','mode':'keyword','keyword':product['keyword'],'sort':'relevancy','maxProducts':max_items,'fetchDetail':False},max_items=max_items,max_total_charge_usd=cap)
        if not result or result.get('status')!='SUCCEEDED':raise RuntimeError('Provider run failed')
        raw=client.dataset(result['defaultDatasetId']).list_items(limit=max_items).items
        own=OWN_SHOPS|{str(p['own_shop_id']) for p in products() if p.get('own_shop_id')}
        for item in raw:
            considered+=1
            title=item.get('name') or item.get('title') or '';url=item.get('url') or item.get('product_url') or ''
            shop,ident=parsed_ids(url)
            if not shop or shop in own or not candidate_match(title,product['keyword']):continue
            try:price=Decimal(str(item.get('price')))
            except Exception:continue
            if not price.is_finite() or price<=0 or price>99999999:continue
            seller=item.get('shop_name') or ((item.get('shop') or {}).get('name') if isinstance(item.get('shop'),dict) else None)
            row={'product_id':product['id'],'shop_id':shop,'item_id':ident,'seller_name':str(seller)[:255] if seller else None,'title':str(title)[:2000],'url':url[:500],'price':float(price),'status':'REVIEW','match_hint':'Keyword matched; manually verify variant and price','snapshot_date':dt.date.today().isoformat()}
            db().table('fs_competitor_listings').upsert(row,on_conflict='product_id,url,snapshot_date',ignore_duplicates=True).execute();n+=1
        message=f'Checked {considered} provider results; saved {n} matching candidates for review.';status='COMPLETED'
    except Exception as e:status='FAILED';message=f'{type(e).__name__}: {str(e)[:230]}'
    finally:
        try:db().table('fs_competitor_jobs').update({'status':status,'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),'candidate_count':considered,'saved_count':n,'message':message}).eq('id',jobid).execute()
        finally:LOCK.release()

@app.post('/api/scrape')
@protected
def scrape():
    d=request.get_json(silent=True) or {}
    if d.get('confirm_paid') is not True:return jsonify(error='Confirm this paid Apify run'),400
    if not os.getenv('APIFY_TOKEN'):return jsonify(error='Set APIFY_TOKEN in .env'),400
    try:pid=int(d.get('product_id'))
    except Exception:return jsonify(error='Invalid product'),400
    p=next((x for x in products() if x['id']==pid and x['active']),None)
    if not p:return jsonify(error='Product not found or inactive'),404
    last=db().table('fs_competitor_jobs').select('started_at').eq('product_id',pid).order('started_at',desc=True).limit(1).execute().data
    if last:
        when=dt.datetime.fromisoformat(last[0]['started_at'].replace('Z','+00:00'))
        if (dt.datetime.now(dt.timezone.utc)-when).total_seconds()<300:return jsonify(error='5-minute cooldown after last run'),429
    if not LOCK.acquire(False):return jsonify(error='Another scrape is still running'),409
    try:
        job=db().table('fs_competitor_jobs').insert({'product_id':pid,'status':'STARTED','requested_by':session['user_id']}).execute().data[0]
        threading.Thread(target=collect_worker,args=(p,session['user_id'],job['id']),daemon=True).start()
        return jsonify(job_id=job['id'],message='Collection started; check Scraping Jobs for results'),202
    except Exception:
        LOCK.release();raise

@app.errorhandler(Exception)
def error(e):
    app.logger.exception('Request failed')
    return jsonify(error='Server error. Check the Python terminal.'),500

if __name__=='__main__':
    if not config_ok():print('Configure .env using .env.example (and create a Supabase staff account)');raise SystemExit(1)
    app.run(host='127.0.0.1',port=5050,debug=False)
