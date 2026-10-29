"""Search and group user-supplied Shopee catalog items for staff product selection."""
import re
from matching import match_detail, name_tokens, pack


def search_catalog(rows, query, limit=30):
    query = ' '.join(str(query or '').split())
    if len(query) < 2:
        return []
    tokens = set(name_tokens(query))
    if not tokens:
        return []
    matching = []
    for row in rows:
        title = row.get('title') or ''
        item_tokens = set(name_tokens(title))
        overlap = len(tokens & item_tokens)
        if overlap == 0:
            continue
        if len(tokens) >= 2 and overlap < min(2, len(tokens)):
            continue
        exact = tokens.issubset(item_tokens)
        score = (1 if exact else 0, overlap / len(tokens), overlap / max(len(item_tokens), 1))
        matching.append((score, row))
    matching.sort(key=lambda x:(x[0], x[1].get('source',''), x[1].get('title','')), reverse=True)
    return [row for _,row in matching[:limit]]


def catalog_for_product(rows, product):
    """Return all exact-name+pack matched listings; do not guess ambiguous matches."""
    keyword = product.get('keyword') or product.get('name') or ''
    expected = product.get('expected_pack') or ''
    selected = [r for r in rows if match_detail(r.get('title',''), keyword, expected)[0]]
    # An explicitly saved own product URL should always appear if known in the catalog.
    own_shop, own_item = str(product.get('own_shop_id') or ''),str(product.get('own_item_id') or '')
    for row in rows:
        if own_shop and own_item and str(row['shop_id'])==own_shop and str(row['item_id'])==own_item and row not in selected:
            selected.append(row)
    return sorted(selected,key=lambda r:(r['source'],r['title'],r['item_id']))
