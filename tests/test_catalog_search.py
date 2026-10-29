import unittest
from catalog_search import search_catalog,catalog_for_product
from own_catalog import bundled_catalog

class CatalogSearchTests(unittest.TestCase):
    def setUp(self): self.rows=bundled_catalog()
    def test_search_both_shops(self):
        results=search_catalog(self.rows,'ORAC KIDS IMMUNE BOOSTER',100)
        shops={r['source'] for r in results}
        self.assertIn('FirstWell',shops)
        self.assertIn('Probiotickids',shops)
    def test_search_unknown(self):
        self.assertFalse(search_catalog(self.rows,'AFAKENEWWORD XYZZY'))
    def test_exact_pack(self):
        rows=[{'title':'ORAC KIDS IMMUNE BOOSTER 5g x 6','source':'FirstWell','item_id':'1','shop_id':'2'},
              {'title':'ORAC KIDS IMMUNE BOOSTER 5g x 12','source':'Probiotickids','item_id':'2','shop_id':'3'}]
        self.assertEqual(len(catalog_for_product(rows,{'keyword':'ORAC KIDS IMMUNE BOOSTER 5g x 6','expected_pack':'5g x 6'})),1)
if __name__=='__main__':unittest.main()
