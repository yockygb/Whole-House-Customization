"""Regression guard: the customer-facing quote page never displays profit."""
from pathlib import Path
from html.parser import HTMLParser
import re,unittest

ROOT=Path(__file__).resolve().parents[1]

class PageParser(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.text=[]
    def handle_starttag(self,tag,attrs):
        fields=dict(attrs)
        if 'id' in fields:self.ids.append(fields['id'])
    def handle_data(self,data):self.text.append(data)

class CustomerPageTests(unittest.TestCase):
    def test_no_profit_element_or_label_in_page(self):
        page=PageParser();page.feed((ROOT/'web/studio.html').read_text(encoding='utf-8'))
        self.assertNotIn('profit',page.ids)
        self.assertNotIn('Gross profit',' '.join(page.text))
        self.assertNotIn('毛利',' '.join(page.text))
    def test_customer_totals_are_retained(self):
        page=PageParser();page.feed((ROOT/'web/studio.html').read_text(encoding='utf-8'))
        for field in ('subtotal','deposit','grandTotal','discount','depositPercent'):self.assertIn(field,page.ids)
    def test_render_does_not_bind_internal_totals(self):
        script=(ROOT/'web/studio.js').read_text(encoding='utf-8')
        render=script[script.index('function render(){'):script.index('function duplicate(')]
        self.assertNotIn('gross_profit',render)
        self.assertNotIn('supply_total',render)
        self.assertNotIn("$('profit')",render)
    def test_categories_use_dropdown_and_rooms_can_be_duplicated(self):
        page=PageParser();page.feed((ROOT/'web/studio.html').read_text(encoding='utf-8'))
        self.assertIn('categorySelect',page.ids)
        self.assertNotIn('categoryTabs',page.ids)
        self.assertIn('addRoomBtn',page.ids)
        script=(ROOT/'web/studio.js').read_text(encoding='utf-8')
        self.assertIn('function addRoomInstance()',script)
        self.assertIn('function syncRoomOptions(',script)
    def test_entry_memory_is_scoped_to_quote_and_image_paste_works_in_drawing(self):
        script=(ROOT/'web/studio.js').read_text(encoding='utf-8')
        self.assertIn('function currentEntryDrafts()',script)
        self.assertIn('S.entryDrafts[S.q.id]',script)
        self.assertIn("if($('modal').open&&!$('drawingFile'))return",script)
        self.assertIn('await drawingPasteHandler?.(image)',script)
    def test_room_label_is_not_repeated_when_english_falls_back_to_chinese(self):
        script=(ROOT/'web/studio.js').read_text(encoding='utf-8')
        self.assertIn('function roomDisplay(it,line)',script)
        self.assertIn('${esc(roomDisplay(it,l))}',script)
    def test_management_exposes_category_delete_and_persistent_order(self):
        script=(ROOT/'web/studio.js').read_text(encoding='utf-8')
        self.assertIn('data-delete-category',script)
        self.assertIn("api('/api/catalogue/order','POST'",script)

if __name__=='__main__':unittest.main(verbosity=2)
