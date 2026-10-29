import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from matching import match_detail
from own_catalog import bundled_catalog, classify, read_xlsx_catalog

class MatchingTests(unittest.TestCase):
    def test_expected_variations_match(self):
        for title in ('ORAC KIDS IMMUNE BOOSTER 5GMx6 Sachets EXP 2028',
                      'ORAC KIDS Immune Booster 5g x 6 Sachets',
                      'ORAC Kids immune booster 6 x 5g sachets'):
            self.assertTrue(match_detail(title,'ORAC KIDS IMMUNE BOOSTER 5GMx6','5g x 6')[0],title)
    def test_wrong_pack_fails(self):
        self.assertFalse(match_detail('ORAC KIDS IMMUNE BOOSTER 5g x 12 sachets','ORAC KIDS IMMUNE BOOSTER 5GMx6','5g x 6')[0])
    def test_other_product_fails(self):
        self.assertFalse(match_detail('Orac Kids Pastilles 12s','ORAC KIDS IMMUNE BOOSTER 5GMx6','5g x 6')[0])
    def test_own_catalog(self):
        self.assertEqual(len(bundled_catalog()),733)
        self.assertEqual(classify('1688602696','57958359680')['own_source'],'FirstWell')
        self.assertEqual(classify('994773440','25500645266')['own_source'],'Probiotickids')
        self.assertEqual(classify('1688602696','99999999')['own_match'],'KNOWN_SHOP')
        self.assertEqual(classify('12345678','57958359680')['own_match'],'ID_CONFLICT')
        self.assertEqual(classify('999','888')['own_shop'],False)
    def test_bundled_id_uniqueness(self):
        ids={(r['shop_id'],r['item_id']) for r in bundled_catalog()}
        self.assertEqual(len(ids),733)

if __name__=='__main__': unittest.main()
