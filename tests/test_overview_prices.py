import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Load the pure aggregation function without importing Flask / Supabase.
import ast
source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "build_price_overview")
ns = {"owned": lambda *_: None, "match_detail": lambda *_: None}
exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), ns)
build_price_overview = ns["build_price_overview"]

class OverviewTests(unittest.TestCase):
    def test_approved_competitor_only_and_latest_snapshot(self):
        product={'id':1,'name':'QV Dermcare 200g','keyword':'QV Dermcare 200g','expected_pack':'200g','our_price':110}
        def fake_owned(shop_id,item_id,ref,ps): return {'own_shop':str(shop_id)=='994773440'}
        def fake_match(title,keyword,pack): return (title.startswith('QV'), 'test')
        data=[
          {'product_id':1,'title':'QV Dermcare 200g','shop_id':'123','price':90,'status':'APPROVE','snapshot_date':'2026-10-01'},
          {'product_id':1,'title':'QV Dermcare 200g','shop_id':'456','price':100,'status':'APPROVE','snapshot_date':'2026-10-02'},
          {'product_id':1,'title':'QV Dermcare 200g','shop_id':'789','price':120,'status':'APPROVE','snapshot_date':'2026-10-02'},
          {'product_id':1,'title':'QV Dermcare 200g','shop_id':'994773440','price':1,'status':'APPROVE','snapshot_date':'2026-10-02'},
          {'product_id':1,'title':'QV Dermcare 200g','shop_id':'111','price':2,'status':'REVIEW','snapshot_date':'2026-10-02'},
          {'product_id':1,'title':'Other brand','shop_id':'222','price':3,'status':'APPROVE','snapshot_date':'2026-10-02'},
        ]
        with patch.dict(build_price_overview.__globals__,{'owned':fake_owned,'match_detail':fake_match}):
            overview=build_price_overview([product],data,[])
        row=overview['products'][0]
        self.assertEqual((row['lowest'],row['average'],row['highest']),(100,110,120))
        self.assertEqual(row['gap_rm'],10)
        self.assertEqual(row['approved'],3)
        self.assertEqual(len(row['history']),2)
        self.assertEqual(overview['pending'],1)

if __name__=='__main__':unittest.main()
