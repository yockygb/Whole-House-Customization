"""Generated add-on remarks are bilingual in Excel and print/PDF HTML."""
import sys,tempfile,re
from pathlib import Path
import unittest
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.engine import Item,load_config,compute_quote
from export.descriptions import remark
from export import xlsx
from export.print_html import render as render_print
from openpyxl import load_workbook
from openpyxl.cell.rich_text import CellRichText,TextBlock

class BilingualRemarkTests(unittest.TestCase):
    def setUp(self):
        self.cfg=load_config(str(ROOT/'data/factory-pricing.json'))
        self.tmp=tempfile.TemporaryDirectory(prefix='whole-house-customization-remarks-')
        self.old_pics=xlsx.PIC_DIR;xlsx.PIC_DIR=str(Path(self.tmp.name)/'pictures')
    def tearDown(self):
        xlsx.PIC_DIR=self.old_pics
        import gc
        gc.collect();self.tmp.cleanup()
    def calculate(self,**fields):
        d=dict(room='厨房',cat='custom_cabinet',material='body_particle',
               length_mm=1200,height_mm=1800,depth_mm=600,qty=1)
        d.update(fields)
        lines,summary=compute_quote(self.cfg,[Item.from_dict(d)])
        return lines[0],summary
    def test_direct_led_has_both_languages_and_accessories(self):
        ln,_=self.calculate(led_type='yes',led_qty=2,led_unit='m',led_power=True,led_sensor=True)
        en,cn=remark(ln,self.cfg)
        for word in ('LED Strip 2 m','Power Supply','Receiver + Sensor'):self.assertIn(word,en)
        for word in ('灯带 2 米','电源','接收器','感应器'):self.assertIn(word,cn)
        self.assertIsNone(re.search('[\u4e00-\u9fff]',en))
    def test_legacy_led_addons_use_matching_units(self):
        ln,_=self.calculate(extras={'led':3,'led_power':1,'led_sensor':1})
        en,cn=remark(ln,self.cfg)
        self.assertIn('LED Strip 3 m',en);self.assertIn('灯带 3 米',cn)
        self.assertIn('LED Power Supply × 1',en);self.assertIn('灯带电源 × 1',cn)
        self.assertIn('Receiver + Sensor × 1',en);self.assertIn('接收器 + 感应器 × 1',cn)
    def test_quartz_sink_and_baskets_have_matching_languages(self):
        ln,_=self.calculate(cat='base_cabinet',material='particle',height_mm=900,
                            extras={'quartz':1,'sink':1,'pull_down':1,'tall_basket':1,'dish_basket':1})
        en,cn=remark(ln,self.cfg)
        for a,b in [('Quartz Countertop','石英石台面'),('Sink','水槽'),('Pull-down Rack','下拉架'),('Tall Cabinet Pull-out Basket','高柜联动拉篮'),('Dish Basket','碗碟拉篮')]:
            self.assertIn(a,en);self.assertIn(b,cn)
    def test_glass_door_own_dimensions_are_bilingual(self):
        ln,_=self.calculate(height_mm=500,extras={'glass_door':1},
                            extras_size={'glass_door':{'w_mm':600,'h_mm':400}})
        en,cn=remark(ln,self.cfg)
        self.assertIn('Glass Door 600 × 400 mm',en)
        self.assertIn('玻璃门 600 × 400 毫米',cn)
        self.assertIn('ft²',en);self.assertIn('平方英尺',cn)
    def test_feet_are_not_mislabeled_as_metres(self):
        ln,_=self.calculate(led_type='yes',led_qty=6.5,led_unit='ft')
        en,cn=remark(ln,self.cfg)
        self.assertIn('6.5 ft',en);self.assertIn('6.5 英尺',cn)
    def test_zero_priced_selected_led_still_has_a_description(self):
        ln,_=self.calculate(led_type='yes',led_qty=2,led_price=0)
        self.assertEqual(ln.led_amount,0)
        en,cn=remark(ln,self.cfg)
        self.assertIn('LED Strip 2 m',en);self.assertIn('灯带 2 米',cn)
    def test_configured_bilingual_names_are_respected(self):
        self.cfg.raw['led']['label_en']='Task Light'
        self.cfg.raw['led']['label']='工作灯'
        ln,_=self.calculate(led_type='yes',led_qty=2)
        en,cn=remark(ln,self.cfg)
        self.assertIn('Task Light 2 m',en);self.assertIn('工作灯 2 米',cn)
    def test_excel_customer_and_internal_have_english_then_chinese(self):
        ln,summary=self.calculate(led_type='yes',led_qty=2,led_power=True,led_sensor=True)
        for kind in ('customer','internal'):
            path=Path(self.tmp.name)/(kind+'.xlsx')
            xlsx.export_workbook(str(path),self.cfg,{'quote_no':'BILINGUAL'},[ln],summary,kind)
            w=load_workbook(path,rich_text=True);sheet=w.worksheets[0]
            row=next(row for row in sheet if row[0].value==1 and row[1].value is not None)
            text=str(row[10].value)
            self.assertIn('LED Strip 2 m',text);self.assertIn('\n含 灯带 2 米',text)
            self.assertIsInstance(row[10].value,CellRichText)
            blocks=[b for b in row[10].value if isinstance(b,TextBlock) and b.text.strip()]
            self.assertGreater(blocks[0].font.sz,blocks[-1].font.sz)
            self.assertTrue(str(row[9].value).startswith('='))
    def test_print_customer_and_internal_have_both_languages(self):
        ln,summary=self.calculate(led_type='yes',led_qty=2,led_power=True,led_sensor=True)
        for kind in ('customer','internal'):
            html=render_print({'quote_no':'BILINGUAL'},[ln],summary,self.cfg,kind=kind)
            cell=re.search(r"<td class='rmk'>(.*?)</td>",html,re.S).group(1)
            self.assertIn('LED Strip 2 m',cell);self.assertIn('灯带 2 米',cell)
            self.assertLess(cell.index("class='en'"),cell.index("class='cn'"))

if __name__=='__main__':unittest.main(verbosity=2)
