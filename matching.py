"""Conservative Shopee title matching. Never claim a candidate is a verified product."""
import html
import re
import unicodedata

UNIT = r'(?:mg|ml|g|gm|gram|grams|kg|pcs|pc|sachets?|tablets?|capsules?|tabs?)'
PACK = re.compile(r'(?<!\d)(\d+(?:\.\d+)?)\s*(mg|ml|g|gm|gram|grams|kg)\s*[x×*]\s*(\d+)', re.I)
PACK_REVERSE = re.compile(r'(?<!\d)(\d+)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(mg|ml|g|gm|gram|grams|kg)', re.I)
COUNT = re.compile(r'(?<!\d)(\d+)\s*(?:sachets?|packets?|packs?|tablets?|capsules?|pcs|pieces)\b', re.I)
DOSE = re.compile(r'(?<!\d)(\d+(?:\.\d+)?)\s*(mg|ml|g|gm|gram|grams|kg)\b', re.I)


def standard(text):
    s = unicodedata.normalize('NFKC', html.unescape(str(text or ''))).casefold()
    s = s.replace('×', 'x').replace('*', 'x')
    s = re.sub(r'(?<=\d)\s*(?:grams?|gm)\b', 'g', s)
    return s


def dosage(s):
    m = DOSE.search(standard(s))
    return (m.group(1).rstrip('0').rstrip('.') if '.' in m.group(1) else m.group(1), 'g' if m.group(2) in ('gm','gram','grams') else m.group(2)) if m else None


def pack(s):
    s = standard(s)
    m = PACK.search(s)
    if m:
        value, unit, count = m.groups()
        return (str(float(value)).removesuffix('.0'), 'g' if unit in ('gm','gram','grams') else unit, int(count))
    m = PACK_REVERSE.search(s)
    if m:
        count, value, unit = m.groups()
        return (str(float(value)).removesuffix('.0'), 'g' if unit in ('gm','gram','grams') else unit, int(count))
    d = dosage(s)
    count = COUNT.search(s)
    if d and count:
        return d[0], d[1], int(count.group(1))
    return None


def name_tokens(s):
    s = standard(s)
    s = PACK.sub(' ', s)
    s = PACK_REVERSE.sub(' ', s)
    s = DOSE.sub(' ', s)
    s = COUNT.sub(' ', s)
    return [w for w in re.findall(r'[a-z0-9]+', s)
            if w not in {'x', 'exp', 'expiry', 'sachet', 'sachets', 'pack', 'packets', 'packet',
                         'pcs', 'pc', 'tablet', 'tablets', 'capsule', 'capsules', 'piece', 'pieces'}]


def match_detail(title, keyword, expected_pack=''):
    """All distinctive search tokens and exact known pack/dose must match."""
    required = name_tokens(keyword)
    present = set(name_tokens(title))
    if len(required) < 2 or not set(required).issubset(present):
        return False, 'Product name does not match all search keywords'
    target_pack = pack(expected_pack) or pack(keyword)
    title_pack = pack(title)
    if target_pack:
        if title_pack != target_pack:
            return False, 'Pack or size differs, or is not stated clearly'
    else:
        req_dose = dosage(expected_pack) or dosage(keyword)
        if req_dose and dosage(title) != req_dose:
            return False, 'Dosage or size differs'
    return True, 'Search title and pack match; verify the listing manually'


def candidate_match(title, keyword, expected_pack=''):
    return match_detail(title, keyword, expected_pack)[0]
