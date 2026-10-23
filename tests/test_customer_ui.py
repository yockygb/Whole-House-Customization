"""Customer-facing quotation UI regression checks."""
from pathlib import Path
from html.parser import HTMLParser
import unittest

ROOT = Path(__file__).resolve().parents[1]

class PageParser(HTMLParser):
    def __init__(self): super().__init__(); self.ids=[]; self.text=[]
    def handle_starttag(self,tag,attrs):
        fields=dict(attrs)
        if 'id' in fields: self.ids.append(fields['id'])
    def handle_data(self,data): self.text.append(data)

class CustomerPageTests(unittest.TestCase):
    def setUp(self):
        self.page=PageParser(); self.page.feed((ROOT/'web/studio.html').read_text(encoding='utf-8'))
        self.script=(ROOT/'web/studio.js').read_text(encoding='utf-8')

    def test_no_profit_is_shown_on_customer_page(self):
        text=' '.join(self.page.text)
        self.assertNotIn('Gross profit',text); self.assertNotIn('毛利',text)
        render=self.script[self.script.index('function render(){'):self.script.index('function duplicate(')]
        self.assertNotIn('gross_profit',render); self.assertNotIn('supply_total',render)

    def test_customer_totals_and_category_dropdown_are_present(self):
        for field in ('subtotal','deposit','grandTotal','discount','depositPercent','categorySelect'):
            self.assertIn(field,self.page.ids)
        self.assertNotIn('categoryTabs',self.page.ids)

    def test_entry_fields_stay_for_same_quote_and_new_quote_resets_them(self):
        add=self.script[self.script.index('function addItem()'):self.script.index('function preview()')]
        new=self.script[self.script.index('async function newQuote()'):self.script.index('function localDate()')]
        adopt=self.script[self.script.index('function adopt('):self.script.index('async function newQuote()')]
        self.assertIn('else S.q.items.push(it)',add)
        self.assertIn('if(editing)resetEntry()',add)
        self.assertIn('adopt(result)',new)
        self.assertIn('resetEntry()',adopt)

    def test_ctrl_v_pastes_drawing_images_and_dimension_text(self):
        self.assertIn("document.addEventListener('paste'",self.script)
        self.assertIn('drawingPasteHandler?.(file)',self.script)
        self.assertIn('clipboardData?.getData',self.script)

    def test_numbered_rooms_and_bilingual_room_label_are_single(self):
        self.assertIn('function addRoomInstance()',self.script)
        self.assertIn('function roomTemplate(value)',self.script)
        render=self.script[self.script.index('function render(){'):self.script.index('function duplicate(')]
        self.assertIn('l.room_en&&l.room_en!==it.room',render)
        self.assertIn('`${l.room_en} / ${it.room}`:it.room',render)

    def test_management_supports_category_delete_and_shared_option_order(self):
        mgmt=(ROOT/'web/management.js').read_text(encoding='utf-8')
        self.assertIn('data-delete-category',mgmt)
        self.assertIn('api',mgmt)
        self.assertIn('function openChoiceOrder',self.script)
        self.assertIn("api('/api/catalogue/order','POST'",self.script)

if __name__ == '__main__': unittest.main(verbosity=2)
