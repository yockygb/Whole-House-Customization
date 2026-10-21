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

if __name__=='__main__':unittest.main(verbosity=2)
