let csrf = '', tab = 'overview', products = [], allListings = [], catalogInfo = null;
let selectedJob = null, pollHandle = null;
let analysisFilter = 'all';
const $ = selector => document.querySelector(selector);
const safe = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const money = value => value == null ? '—' : 'RM ' + Number(value).toFixed(2);
const getName = id => products.find(p => String(p.id) === String(id))?.name || 'Product #' + id;
const badge = row => row.own_shop ? '<span class="pill owned">' + safe(row.own_label) + '</span>' :
    row.own_match === 'ID_CONFLICT' ? '<span class="pill danger">Check ID conflict</span>' :
    '<span class="pill neutral">Other seller</span>';
async function api(url, options = {}) {
    const headers = {'X-CSRF-Token': csrf, ...options.headers};
    if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    const response = await fetch(url, {...options, headers});
    let data = {};
    try { data = await response.json(); } catch (_) { throw Error('Unexpected response from the server'); }
    if (!response.ok) throw Error(data.error || `HTTP ${response.status}`);
    return data;
}
function inform(message, type='info') { const region = $('#message'); region.textContent = message; region.className = 'message '+type; region.hidden = false; }
function clearMessage() { $('#message').hidden = true; }
async function load() {
    const current = await api('/api/session');
    csrf = current.csrf;
    $('#email').textContent = current.email;
    await refresh();
}
async function refresh() {
    const values = await Promise.all([api('/api/products'), api('/api/listings'), api('/api/catalog')]);
    products = values[0].products;
    allListings = values[1].listings;
    catalogInfo = values[2];
    render();
}
function changeTab(next) {
    if (pollHandle) { clearTimeout(pollHandle); pollHandle = null; }
    tab = next; clearMessage(); render();
}
function render() {
    document.querySelectorAll('nav button').forEach(button => button.classList.toggle('selected', button.dataset.tab === tab));
    if (tab === 'overview') return overview();
    if (tab === 'products') return manage();
    if (tab === 'listings') return listings();
    if (tab === 'shops') return shops();
    if (tab === 'catalog') return catalog();
    if (tab === 'scraping') return scraping();
}
function overview() {
    const view=$('#view');
    view.innerHTML='<h2>Price Intelligence Dashboard</h2><p class="subtitle">Loading reviewed competitor prices...</p>';
    api('/api/overview').then(data=>{
        if(tab!=='overview')return;
        const ranked=data.products.filter(r=>r.gap_rm!==null).slice().sort((a,b)=>b.gap_rm-a.gap_rm);
        const selected=ranked[0] || data.products.find(r=>r.history.length>0);
        const actionRows=data.products.map(r=>({...r, actionLabel:analysisAction(r)}));
        const actionable=actionRows.filter(r=>['PRICE_RISK','REFRESH_SNAPSHOT','REVIEW_COMPETITORS','ADD_OUR_PRICE'].includes(r.action));
        view.innerHTML=`<div class="dashboard-heading"><div><div class="eyebrow">FIRSTSTEP · SHOPEE MARKET INTELLIGENCE</div>
          <h2>Price Intelligence Dashboard</h2><p class="subtitle">Compare our prices against manually approved competitors only. FirstWell and Probiotickids are excluded.</p></div>
          <div class="dashboard-action"><button id="reloadOverview" class="secondary">↻ Refresh analysis</button></div></div>
          <div class="cards dashboard-kpis">
            <div class="card metric"><small>Tracked products</small><strong>${data.products.length}</strong><span>In your monitoring list</span></div>
            <div class="card metric"><small>Products with comparison</small><strong>${data.products_compared}</strong><span>With our price and approved competitors</span></div>
            <div class="card metric"><small>Above lowest competitor</small><strong>${data.priced_above_lowest}</strong><span>Our price is higher</span></div>
            <div class="card metric"><small>Average gap to lowest</small><strong>${data.average_gap_rm===null?'—':money(data.average_gap_rm)}</strong><span>Across comparable products</span></div>
            <div class="card metric"><small>Pending review</small><strong>${data.pending}</strong><span>Listings not approved yet</span></div>
          </div>
          <section class="executive-summary"><div class="executive-intro"><div class="eyebrow">MANAGEMENT BRIEF · ${safe(data.as_of)}</div><h3>Where should the team act first?</h3><p>Price positioning is based on approved matching listings, not all Shopee search results.</p></div><div class="executive-pill"><b>${actionable.length}</b><span>Products to check</span></div><div class="executive-pill"><b>${data.stale_products}</b><span>Snapshots older than 30 days</span></div><div class="executive-pill"><b>${data.missing_comparison}</b><span>Without a comparable price</span></div></section>
          <section class="panel"><div class="dashboard-heading"><div><h3>Business action priorities</h3><p class="muted">Use this queue before making pricing decisions; old snapshots are flagged separately.</p></div><label class="chart-choice">View<select id="analysisFilter"><option value="all">All active products</option><option value="PRICE_RISK">Above competitor price</option><option value="PRICE_ADVANTAGE">Price advantage</option><option value="REFRESH_SNAPSHOT">Outdated competitor snapshot</option><option value="missing">Missing comparison</option></select></label></div><div id="priorityTable"></div></section>
          <div class="dashboard-two">
            <section class="panel"><h3>Our price vs competitor prices</h3><p class="muted">RM · latest approved snapshot for each product</p>
              <div id="compareChart" class="compare-chart"></div></section>
            <section class="panel"><h3>Biggest price gaps</h3><p class="muted">Our price minus lowest approved competitor; positive means we cost more.</p>
              <div id="gapRanking"></div></section>
          </div>
          <section class="panel"><div class="dashboard-heading"><div><h3>Historical competitor price trend</h3><p class="muted">Approved snapshots, not live Shopee prices. At least two dates required for a line.</p></div>
            <label class="chart-choice">Product<select id="historyProduct">${data.products.map(r=>`<option value="${r.product.id}" ${selected?.product.id===r.product.id?'selected':''}>${safe(r.product.name)}</option>`).join('')}</select></label></div>
            <div id="trendChart" class="trend-chart"></div></section>
          <section class="panel table-wrap"><h3>Product-level price analysis</h3><table><thead><tr><th>Tracked product</th><th>Our price</th><th>Lowest</th><th>Average</th><th>Highest</th><th>Gap vs lowest</th><th>Approved offers</th><th>Snapshot date</th></tr></thead><tbody>
          ${data.products.map(r=>`<tr><td><strong>${safe(r.product.name)}</strong></td><td>${money(r.product.our_price)}</td><td>${money(r.lowest)}</td><td>${money(r.average)}</td><td>${money(r.highest)}</td>
            <td>${r.gap_rm===null?'—':`<span class="${r.gap_rm>0?'bad-gap':r.gap_rm<0?'good-gap':''}">${r.gap_rm>0?'+':''}${money(r.gap_rm)}</span><small class="block muted">${r.gap_percent===null?'':(r.gap_percent>0?'+':'')+r.gap_percent.toFixed(1)+'%'}</small>`}</td>
            <td>${r.current_count}</td><td>${safe(r.snapshot_date||'Not yet approved')}</td></tr>`).join('')}</tbody></table></section>
          <p class="muted dashboard-footnote">${safe(data.note)} No competitor profit or margin is inferred from prices alone.</p>`;
        $('#reloadOverview').onclick=overview;
        const filter=$('#analysisFilter');filter.value=analysisFilter;
        function updateActions(){const subset=actionRows.filter(r=>analysisFilter==='all'||(analysisFilter==='missing'?r.gap_rm===null:r.action===analysisFilter));$('#priorityTable').innerHTML=priorityTable(subset);}
        filter.onchange=()=>{analysisFilter=filter.value;updateActions();};updateActions();
        $('#compareChart').innerHTML=priceComparison(data.products);
        $('#gapRanking').innerHTML=gapRanking(ranked);
        const choose=$('#historyProduct');
        function updateHistory(){ const r=data.products.find(x=>String(x.product.id)===choose.value); $('#trendChart').innerHTML=trendGraph(r); }
        choose.onchange=updateHistory; updateHistory();
    }).catch(error=>inform(error.message,'error'));
}
function analysisAction(r){
    const labels={PRICE_RISK:'Evaluate price gap',PRICE_ADVANTAGE:'Competitive advantage',REFRESH_SNAPSHOT:'Refresh market evidence',ADD_OUR_PRICE:'Enter our price',REVIEW_COMPETITORS:'Approve comparable offers',AT_PAR:'Price at parity'};
    return labels[r.action] || 'Review';
}
function priorityTable(rows){
    if(!rows.length) return '<div class="empty-state">No products in this category.</div>';
    const priority={PRICE_RISK:0,REFRESH_SNAPSHOT:1,ADD_OUR_PRICE:2,REVIEW_COMPETITORS:3,AT_PAR:4,PRICE_ADVANTAGE:5};
    rows=rows.slice().sort((a,b)=>(priority[a.action]??6)-(priority[b.action]??6)||(b.gap_rm??-9999)-(a.gap_rm??-9999));
    return `<div class="table-wrap"><table class="action-table"><thead><tr><th>Product</th><th>Decision signal</th><th>Our price</th><th>Lowest competitor</th><th>Gap</th><th>Evidence</th></tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${safe(r.product.name)}</strong><small class="block muted">${safe(r.product.expected_pack||'Pack not specified')}</small></td><td><span class="action-tag tag-${safe(r.action)}">${safe(r.actionLabel)}</span></td><td>${money(r.product.our_price)}</td><td>${money(r.lowest)}</td><td><strong class="${r.gap_rm>0?'bad-gap':r.gap_rm<0?'good-gap':''}">${r.gap_rm===null?'—':(r.gap_rm>0?'+':'')+money(r.gap_rm)}</strong></td><td>${r.snapshot_date?safe(r.snapshot_date)+' · '+r.current_count+' offer(s)':'No approved match'}${r.age_days>30?'<small class="block bad-gap">Outdated: '+r.age_days+' days</small>':''}</td></tr>`).join('')}</tbody></table></div>`;
}
function priceComparison(rows){
    const valid=rows.filter(r=>r.lowest!==null&&r.product.our_price!==null);
    if(!valid.length)return '<div class="empty-state">No approved competitor prices yet. Review matching listings and enter your own price to see comparisons.</div>';
    const max=Math.max(1,...valid.flatMap(r=>[Number(r.product.our_price),Number(r.lowest),Number(r.average||0)]));
    return '<div class="chart-legend"><span class="legend-own">Our price</span><span class="legend-competitor">Lowest competitor</span></div>'+valid.map(r=>{
        const own=Number(r.product.our_price),low=Number(r.lowest);
        return `<div class="compare-item"><div class="compare-name" title="${safe(r.product.name)}">${safe(r.product.name)}</div>
          <div class="bar-track"><div class="bar-own" style="width:${Math.min(100,100*own/max)}%"></div></div>
          <div class="bar-track"><div class="bar-comp" style="width:${Math.min(100,100*low/max)}%"></div></div>
          <div class="compare-values">${money(own)} <span>vs</span> ${money(low)}</div></div>`;
    }).join('');
}
function gapRanking(rows){
    if(!rows.length)return '<div class="empty-state">Add our prices and approve matching competitors to see price gaps.</div>';
    return '<div class="gap-list">'+rows.slice(0,6).map((r,i)=>`<div class="gap-item"><span class="gap-index">${i+1}</span><div class="gap-name">${safe(r.product.name)}</div><div class="gap-value ${r.gap_rm>0?'bad-gap':r.gap_rm<0?'good-gap':''}">${r.gap_rm>0?'+':''}${money(r.gap_rm)}</div></div>`).join('')+'</div>';
}
function trendGraph(row){
    if(!row||!row.history.length)return '<div class="empty-state">No approved historical competitor snapshots for this product.</div>';
    const entries=row.history;
    if(entries.length<2)return `<div class="empty-state">Only one approved snapshot (${safe(entries[0].date)}). A trend requires two or more dates.</div>`;
    const w=820,h=250,left=60,right=22,top=24,bottom=45;
    const values=entries.flatMap(x=>[x.lowest,x.average,x.highest]);
    let min=Math.min(...values),max=Math.max(...values);if(min===max){min-=1;max+=1;} else{const pad=(max-min)*.1;min=Math.max(0,min-pad);max+=pad;}
    const X=i=>left+(w-left-right)*(i/(entries.length-1));
    const Y=v=>top+(h-top-bottom)*(1-(v-min)/(max-min));
    const line=(key,color)=>`<polyline fill="none" stroke="${color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" points="${entries.map((r,i)=>X(i)+','+Y(r[key])).join(' ')}"/>`;
    const ticks=Array.from({length:4},(_,i)=>min+(max-min)*i/3);
    return `<div class="chart-legend"><span class="legend-low">Lowest</span><span class="legend-avg">Average</span><span class="legend-high">Highest</span></div>
      <svg class="price-trend-svg" viewBox="0 0 ${w} ${h}" role="img" aria-label="Historical approved competitor price trends">
      ${ticks.map(v=>`<line x1="${left}" x2="${w-right}" y1="${Y(v)}" y2="${Y(v)}" stroke="#e5ebe8"/><text x="${left-10}" y="${Y(v)+4}" font-size="12" fill="#668078" text-anchor="end">${v.toFixed(0)}</text>`).join('')}
      ${line('lowest','#0f766e')}${line('average','#cf9239')}${line('highest','#a56eb3')}
      ${entries.map((r,i)=>`<text x="${X(i)}" y="${h-14}" font-size="11" fill="#668078" text-anchor="middle">${safe(r.date.slice(5))}</text>`).join('')}</svg>
      <p class="muted">${entries.length} approved snapshot dates. Individual listing counts can differ between dates.</p>`;
}
function manage() {
    const activeProducts = products.filter(p => p.active);
    $('#view').innerHTML=`<h2>Manage Products</h2><p class="subtitle">Add a product once, update our price any time, or remove a product from active tracking. Historical competitor prices are retained.</p>
    <div class="panel"><h3>Add a tracked product</h3><form id="add" class="grid">
    <label>Exact product name<input name="name" required placeholder="ORAC KIDS IMMUNE BOOSTER 5GMx6"></label>
    <label>Search keywords<input name="keyword" required placeholder="ORAC KIDS IMMUNE BOOSTER 5GMx6"></label>
    <label>Expected pack<input name="pack" placeholder="5g x 6"></label>
    <label>Our price (RM)<input name="our_price" type="number" step=".01" min="0.01"></label>
    <label>Our Shopee listing URL (optional)<input name="own_url" placeholder="https://shopee.com.my/..."></label>
    <button type="submit">Add Product</button></form></div>
    <div class="panel table-wrap" id="productLinks"><p>Loading tracked products...</p></div>`;
    $('#add').onsubmit=async event=>{
        event.preventDefault();
        const data=Object.fromEntries(new FormData(event.target));
        try { const result=await api('/api/products',{method:'POST',body:JSON.stringify(data)}); inform('Added product #'+result.product.id,'success'); await refresh(); }
        catch (error) { inform(error.message,'error'); }
    };
    api('/api/products/catalog-links').then(data=>{
        if(tab!=='products')return;
        $('#productLinks').innerHTML=`<h3>Active tracked products (${activeProducts.length})</h3>
        <p class="muted">One tracked product can have listings in FirstWell and Probiotickids. Edit the price here; Remove safely archives the tracked product instead of deleting historical listings.</p>
        <table><thead><tr><th>ID</th><th>Tracked product</th><th>Own-shop IDs from Excel</th><th>Our Price (RM)</th><th>Actions</th></tr></thead><tbody>
        ${activeProducts.map(p=>{const refs=data.links[String(p.id)]||[];return `<tr><td>${p.id}</td><td><strong>${safe(p.name)}</strong><small class="block muted">Pack: ${safe(p.expected_pack||'not specified')}</small></td><td>${refs.length?refs.map(r=>`<div class="catalog-link"><span class="pill owned">${safe(r.source)}</span> <code>${safe(r.shop_id)}</code> / <code>${safe(r.item_id)}</code><div class="muted">${safe(r.title)}</div></div>`).join(''):'<span class="muted">No matching Excel Item ID. You may verify your own URL separately.</span>'}</td>
        <td>${money(p.our_price)}</td><td><button type="button" class="compact" data-edit="${p.id}">Edit price</button> <button type="button" class="compact" data-archive="${p.id}">Remove</button></td></tr>`}).join('') || '<tr><td colspan="5">No active tracked products.</td></tr>'}</tbody></table>`;
        document.querySelectorAll('[data-edit]').forEach(button=>button.onclick=async()=>{
            const id=Number(button.dataset.edit), p=activeProducts.find(x=>x.id===id);
            if(!p)return;
            const entered=prompt(`New FirstStep price (RM) for ${p.name}\nLeave blank to clear the price:`, p.our_price==null?'':Number(p.our_price).toFixed(2));
            if(entered===null)return;
            const value=entered.trim();
            if(value!=='' && (!Number.isFinite(Number(value)) || Number(value)<=0 || Number(value)>99999999 || !/^\d+(?:\.\d{1,2})?$/.test(value))) {
                inform('Enter a positive price in RM with up to two decimal places, or leave blank to clear.','error'); return;
            }
            try { await api('/api/products/'+id,{method:'PATCH',body:JSON.stringify({our_price:value})}); await refresh(); inform('Price updated for '+p.name,'success'); }
            catch(error){inform(error.message,'error');}
        });
        document.querySelectorAll('[data-archive]').forEach(button=>button.onclick=async()=>{
            const id=Number(button.dataset.archive),p=activeProducts.find(x=>x.id===id);
            if(!p||!confirm(`Remove ${p.name} from active tracking?\n\nExisting competitor listings and price history will be kept.`))return;
            try { await api('/api/products/'+id+'/archive',{method:'POST',body:JSON.stringify({confirm:true})}); await refresh(); inform('Removed '+p.name+' from active tracking. History was preserved.','success'); }
            catch(error){inform(error.message,'error');}
        });
    }).catch(error=>inform(error.message,'error'));
}
function listings() {
    $('#view').innerHTML=`<h2>Competitor Listings & Match Review</h2>
    <p class="subtitle">Open the real Shopee page before approving. Our two shops are shown but cannot be approved as competitors.</p>
    <div class="panel"><label>Filter by tracked product<select id="filter"><option value="">All products</option>${products.filter(p=>p.active).map(p=>`<option value="${p.id}">${safe(p.name)}</option>`).join('')}</select></label></div>
    <div class="panel table-wrap" id="listingTable"></div>`;
    $('#filter').onchange=drawListings;
    drawListings();
}
function drawListings() {
    const filter=$('#filter').value;
    const rows=allListings.filter(l=>!filter || String(l.product_id)===filter);
    $('#listingTable').innerHTML=`<h3>${rows.length} saved listing${rows.length!==1?'s':''}</h3>
    <table><tr><th>Tracked product</th><th>Shopee listing</th><th>Seller / ownership</th><th>Shop ID</th><th>Item ID</th><th>Price</th><th>Review</th></tr>
    ${rows.map(row=>`<tr class="${row.own_shop?'our-row':''}"><td>${safe(getName(row.product_id))}</td>
    <td><a href="${safe(row.url)}" target="_blank" rel="noopener noreferrer">${safe(row.title)}</a><small class="muted block">${safe(row.snapshot_date)}</small></td>
    <td>${badge(row)}${row.seller_name ? `<small class="block">${safe(row.seller_name)}</small>` : ''}</td>
    <td><code>${safe(row.shop_id || 'Unknown')}</code></td><td><code>${safe(row.item_id || 'Unknown')}</code></td><td>${money(row.price)}</td>
    <td>${row.own_shop ? '<b>Excluded: Our Shop</b>' : `<select id="d${row.id}">${['REVIEW','APPROVE','EXCLUDE','UNAVAILABLE'].map(s=>`<option ${row.status===s?'selected':''}>${s}</option>`).join('')}</select><button class="compact" data-id="${row.id}">Save</button>`}</td></tr>`).join('')}</table>`;
    document.querySelectorAll('#listingTable button[data-id]').forEach(button=>button.onclick=async()=>{
        const id=button.dataset.id;
        const status=$('#d'+id).value;
        let verified=false;
        if (status==='APPROVE') {
            verified=confirm('Did you open the Shopee link and verify exact product, pack, variation and recorded price?');
            if (!verified) return;
        }
        try { await api('/api/listings/'+id+'/decision',{method:'POST',body:JSON.stringify({status,verified})}); await refresh(); inform('Review saved','success'); }
        catch (error) { inform(error.message,'error'); }
    });
}
function shops() {
    const map=new Map();
    for (const [source,shop] of Object.entries(catalogInfo.shops)) map.set(shop,{shop,source,our:true,count:0});
    for (const l of allListings) {
        if (!l.shop_id) continue;
        const row=map.get(l.shop_id) || {shop:l.shop_id,source:l.seller_name || 'Unknown seller',our:l.own_shop,count:0};
        row.count++; if (l.own_shop) {row.our=true;row.source=l.own_source || row.source;}
        map.set(l.shop_id,row);
    }
    $('#view').innerHTML=`<h2>Shop Directory</h2><p class="subtitle">Known shop IDs are read from your two actual Shopee exports — not guessed from names.</p>
    <div class="panel table-wrap"><table><tr><th>Shopee Shop ID</th><th>Shop name / source</th><th>Ownership</th><th>Saved listings</th></tr>
    ${[...map.values()].map(r=>`<tr><td><code>${safe(r.shop)}</code></td><td>${safe(r.source)}</td>
    <td><span class="pill ${r.our?'owned':'neutral'}">${r.our?'OUR SHOP':'Other seller'}</span></td><td>${r.count}</td></tr>`).join('')}</table></div>`;
}
function catalog() {
    $('#view').innerHTML=`<h2>Our Shopee Product IDs</h2><p class="subtitle">Use your two uploaded Mass Update Excel files to identify our own Item IDs automatically.</p>
    <div class="cards"><div class="card">FirstWell <small>Shop ID 1688602696</small><strong>${catalogInfo.counts.FirstWell || 0}</strong> unique Item IDs</div>
    <div class="card">Probiotickids <small>Shop ID 994773440</small><strong>${catalogInfo.counts.Probiotickids || 0}</strong> unique Item IDs</div>
    <div class="card">Total own products<strong>${catalogInfo.total}</strong> known Item IDs</div></div>
    <div class="panel"><h3>Sync the supplied Excel reference lists into Supabase</h3><p>One-click safe upsert. It does not erase historical competitor listings.</p>
    <button id="sync">Sync both built-in Excel catalogs</button></div>
    <div class="panel"><h3>Upload a newer Excel export</h3>
    <form id="catalogUpload" class="grid"><label>Shop<select name="source"><option>FirstWell</option><option>Probiotickids</option></select></label>
    <label>Shopee Mass Update XLSX<input name="file" type="file" accept=".xlsx" required></label><button>Import Product IDs</button></form>
    <p class="muted">The import verifies the shop ID in the Excel file and takes the Product ID from column A. Variation rows are combined into one Item ID.</p></div>`;
    $('#sync').onclick=async()=>{
        if(!confirm('Sync 733 known own-shop Product IDs to Supabase?'))return;
        try {const data=await api('/api/catalog/sync',{method:'POST',body:'{}'});await refresh();inform(`${data.synced} own Item IDs synced to Supabase`,'success');}
        catch(error){inform(error.message,'error')}
    };
    $('#catalogUpload').onsubmit=async event=>{
        event.preventDefault();const form=event.target;
        const source=form.elements.source.value, file=form.elements.file.files[0];
        if (!file) return;
        const fd=new FormData();fd.set('file',file);
        try { const data=await api('/api/catalog/upload/'+encodeURIComponent(source),{method:'POST',body:fd});await refresh();inform(`Imported ${data.imported} ${source} Item IDs to Supabase`,'success'); }
        catch(error) { inform(error.message,'error'); }
    };
}
function scraping() {
    $('#view').innerHTML=`<h2>Shopee Scraping — Top 10 Matching Listings</h2>
    <p class="subtitle">Lists up to 10 actual provider results with matching product name/pack, including FirstWell and Probiotickids.</p>
    <div class="panel"><form id="scrapeForm" class="grid">
      <label>Tracked product<select id="scrapeProduct" name="product_id">${products.filter(p=>p.active).map(p=>`<option value="${p.id}">${safe(p.name)}</option>`).join('')}</select></label>
      <label class="checkline"><input type="checkbox" id="confirmPaid" required> I understand Apify may charge for this run</label>
      <button type="submit" id="startScrape">Start Live Scrape</button>
    </form><p class="muted">Up to 10 relevant results from up to 30 candidate records; fewer is normal. Live scraping requires sufficient Apify credit. Never fabricates results.</p></div>
    <div class="panel" id="ownMatches"><h3>Known own products in Excel</h3><p>Choose a product to compare the two reference files.</p></div>
    <div class="panel" id="scrapeResults"><h3>Top 10 from the latest run</h3><p class="muted">No scrape selected. Start a job or view its previous results below.</p></div>
    <div class="panel" id="scrapeJobs"><h3>Recent jobs</h3><p>Loading...</p></div>`;
    $('#scrapeProduct').onchange=()=>showOwnMatches();
    $('#scrapeForm').onsubmit=async event=>{
        event.preventDefault();
        if(!confirm('Start a potentially paid Apify scrape for this product?')) return;
        try {
            const response=await api('/api/scrape',{method:'POST',body:JSON.stringify({product_id:$('#scrapeProduct').value,confirm_paid:true})});
            selectedJob=response.job_id;inform(response.message,'success');showJobResults(selectedJob);jobs();
        } catch(error) {inform(error.message,'error');}
    };
    showOwnMatches();jobs();
    if (selectedJob) showJobResults(selectedJob);
}
async function showOwnMatches() {
    const slot=$('#ownMatches'),id=$('#scrapeProduct')?.value;
    if (!slot||!id) return;
    try {
        const data=await api('/api/catalog/matches?product_id='+encodeURIComponent(id));
        if(!$('#ownMatches'))return;
        slot.innerHTML=`<h3>Known own products in your Excel files (${data.total})</h3><p class="muted">These are catalog reference records, not live scraped results.</p>
        ${data.matches.length ? `<div class="table-wrap"><table><tr><th>Shop</th><th>Excel Item ID</th><th>Excel Product Name</th></tr>
        ${data.matches.map(x=>`<tr><td><span class="pill owned">${safe(x.source)}</span></td><td><code>${safe(x.item_id)}</code></td><td>${safe(x.title)}</td></tr>`).join('')}</table></div>` : '<p>No exact match in the two Excel exports. The Shop IDs will still be recognized.</p>'}`;
    } catch(error) {slot.innerHTML=`<p class="warning">${safe(error.message)}</p>`;}
}
async function jobs() {
    const slot=$('#scrapeJobs');if(!slot)return;
    try {
        const data=(await api('/api/jobs')).jobs;
        if(!$('#scrapeJobs'))return;
        slot.innerHTML=`<h3>Scraping jobs</h3><div class="table-wrap"><table><tr><th>Product</th><th>Status</th><th>Matches</th><th>When</th><th>Message</th><th>Results</th></tr>
        ${data.map(j=>`<tr><td>${safe(getName(j.product_id))}</td><td>${safe(j.status)}</td><td>${j.saved_count}</td>
        <td>${safe(j.started_at)}</td><td>${safe(j.message||'Running...')}</td><td><button class="compact" data-job="${j.id}">View</button></td></tr>`).join('')}</table></div><button class="compact" id="refreshJobs">Refresh</button>`;
        $('#refreshJobs').onclick=jobs;
        document.querySelectorAll('#scrapeJobs button[data-job]').forEach(button=>button.onclick=()=>{
            selectedJob=Number(button.dataset.job);showJobResults(selectedJob);
        });
    } catch(error) {slot.innerHTML=`<p class="warning">${safe(error.message)}</p>`;}
}
async function showJobResults(jobId) {
    if (pollHandle) {clearTimeout(pollHandle);pollHandle=null;}
    const slot=$('#scrapeResults');if(!slot)return;
    try {
        const response=await api('/api/jobs/'+jobId+'/results');
        if(tab!=='scraping'||selectedJob!==jobId||!$('#scrapeResults'))return;
        const job=response.job, rows=response.listings;
        slot.innerHTML=`<h3>Top ${rows.length} Matching Shopee Listings (Best-selling search) — Job #${job.id}</h3>
        <p class="subtitle">${safe(job.status)} · ${safe(job.message||'Job is running...')}</p>
        ${rows.length?`<div class="table-wrap"><table><tr><th>#</th><th>Real Shopee listing</th><th>Ownership</th><th>Shop ID</th><th>Item ID</th><th>Price</th></tr>
        ${rows.map((r,i)=>`<tr class="${r.own_shop?'our-row':''}"><td>${i+1}</td>
          <td><a href="${safe(r.url)}" target="_blank" rel="noopener noreferrer">${safe(r.title)}</a>${r.seller_name ? `<small class="block muted">${safe(r.seller_name)}</small>` : ''}</td>
          <td>${badge(r)}</td><td><code>${safe(r.shop_id)}</code></td><td><code>${safe(r.item_id)}</code></td><td>${money(r.price)}</td></tr>`).join('')}
        </table></div>`:'<p>No matching Shopee listings have been returned for this job.</p>'}
        <p class="muted">Showing genuine provider listings only. Match is based on name and pack, but staff must verify prices before approval.</p>`;
        if(job.status==='STARTED') pollHandle=setTimeout(()=>{showJobResults(jobId);jobs()},4000);
    } catch(error) {slot.innerHTML=`<p class="warning">${safe(error.message)}</p>`;}
}
function showError(error) { $('#view').innerHTML=`<h2>Unable to load FirstStep</h2><p class="warning">${safe(error.message)}</p>`; }
document.querySelectorAll('nav button').forEach(button=>button.onclick=()=>changeTab(button.dataset.tab));
$('#logout').onclick=async()=>{try{await api('/logout',{method:'POST'});location='/login'}catch(e){inform(e.message,'error')}};
load().catch(showError);
