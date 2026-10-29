"""User-supplied FirstWell / Probiotickids Shopee product catalog.

No credentials or patient data. Product ID is the Shopee *item ID*, not shop ID.
The bundled catalog provides a fallback if the Supabase catalog is not yet synced.
"""
import io
import json
import re
from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

CATALOG_PATH = Path(__file__).parent / 'data' / 'own_catalog.json'
SOURCES = {'FirstWell': '1688602696', 'Probiotickids': '994773440'}
_XNS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


@lru_cache(maxsize=1)
def bundled_catalog():
    if CATALOG_PATH.exists():
        return json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    return []


def classify(shop_id, item_id, catalog=None, additional_shop_ids=()):
    rows = bundled_catalog() if catalog is None else catalog
    shop = str(shop_id or '')
    item = str(item_id or '')
    exact = next((r for r in rows if str(r.get('item_id')) == item and item and
                  str(r.get('shop_id')) == shop), None)
    if exact:
        return {'own_shop': True, 'own_match': 'EXCEL_ITEM', 'own_source': exact['source'],
                'own_label': 'OUR SHOP — '+exact['source']+' (Excel Product ID)'}
    # An item ID matching an Excel file but with a different shop is suspicious.
    collision = next((r for r in rows if str(r.get('item_id')) == item and item), None)
    if collision:
        return {'own_shop': False, 'own_match': 'ID_CONFLICT', 'own_source': collision['source'],
                'own_label': 'ID conflict — check Shopee URL'}
    known = {str(r['shop_id']):r['source'] for r in rows}
    known.update({sid:source for source,sid in SOURCES.items()})
    if shop and shop in known:
        return {'own_shop': True, 'own_match': 'KNOWN_SHOP', 'own_source': known[shop],
                'own_label': 'OUR SHOP — '+known[shop]+' (Shop ID only)'}
    if shop and shop in {str(x) for x in additional_shop_ids}:
        return {'own_shop': True, 'own_match': 'KNOWN_SHOP', 'own_source': 'FirstStep',
                'own_label': 'OUR SHOP — FirstStep (Shop ID only)'}
    return {'own_shop': False, 'own_match': 'OTHER' if shop else 'UNKNOWN', 'own_source': None,
            'own_label': 'Other Shopee seller' if shop else 'Unknown shop'}


def read_xlsx_catalog(file_data, source):
    """Read the two known Shopee Mass Update templates (uses Python stdlib only).

    Requires Product ID / Product Name headers in row 3 and shop ID in D2.
    Rejects unexpected shops rather than accidentally trusting an unrelated file.
    """
    if source not in SOURCES:
        raise ValueError('Choose FirstWell or Probiotickids')
    if len(file_data) > 8_000_000:
        raise ValueError('Excel file is too large (maximum 8 MB)')
    with ZipFile(io.BytesIO(file_data)) as archive:
        for name in ('xl/worksheets/sheet1.xml',):
            info = archive.getinfo(name)
            if info.file_size > 20_000_000:
                raise ValueError('Excel worksheet is too large')
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            info = archive.getinfo('xl/sharedStrings.xml')
            if info.file_size > 15_000_000:
                raise ValueError('Excel strings are too large')
            root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            for entry in root.findall(_XNS+'si'):
                strings.append(''.join((x.text or '') for x in entry.iter(_XNS+'t')))
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        def values(row):
            out = {}
            for cell in row.findall(_XNS+'c'):
                col = re.match(r'[A-Z]+', cell.get('r',''))
                if not col:
                    continue
                v = cell.find(_XNS+'v')
                if cell.get('t') == 'inlineStr':
                    out[col.group()] = ''.join((x.text or '') for x in cell.iter(_XNS+'t'))
                elif v is not None:
                    raw = v.text or ''
                    out[col.group()] = strings[int(raw)] if cell.get('t') == 's' else raw
            return out
        rows = {int(row.get('r','0')):values(row) for row in sheet.iter(_XNS+'row')}
        if rows.get(3,{}).get('A') != 'Product ID' or rows.get(3,{}).get('B') != 'Product Name':
            raise ValueError('Not a supported Shopee Mass Update product file')
        if rows.get(2,{}).get('D') != SOURCES[source]:
            raise ValueError('Excel Shop ID does not match the selected shop')
        result = {}
        for n, row in rows.items():
            if n < 7:
                continue
            item = str(row.get('A','')).strip()
            title = str(row.get('B','')).strip()
            if not re.fullmatch(r'\d{8,16}', item) or not title:
                continue
            if item not in result:
                result[item] = {'source':source,'shop_id':SOURCES[source], 'item_id':item,
                                'title':title[:2000], 'variation_count':0}
            result[item]['variation_count'] += 1
        if not result:
            raise ValueError('No valid Product IDs found')
        return list(result.values())
