"""Clear bundled business data, or fail a release check if it is present."""
from pathlib import Path
import argparse
import ast
import copy
import json
import os
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
AMOUNTS = {'price', 'supply', 'cost', 'quote', 'market', 'price_per_m',
           'power_price', 'sensor_price', 'unit_price', 'led_price',
           'quote_price', 'cost_price'}
OVERRIDES = {'unit_price', 'led_price', 'quote_price', 'cost_price'}
AMOUNT_TEXT = re.compile(r'(?:\b(?:RM|MYR|USD|CNY|RMB)|[$¥￥])\s*\d|(?:单价|价格|供货价|成本价)\s*\d', re.I)


def clear_amounts(value):
    if isinstance(value, list):
        return [clear_amounts(item) for item in value]
    if not isinstance(value, dict):
        return '' if isinstance(value, str) and AMOUNT_TEXT.search(value) else value
    result = {}
    for key, item in value.items():
        if key in OVERRIDES:
            result[key] = None
        elif key in AMOUNTS:
            result[key] = [0, 0] if key == 'market' else 0
        else:
            result[key] = clear_amounts(item)
    return result


def public_seed(raw):
    result = clear_amounts(copy.deepcopy(raw))
    result['meta']['source_note'] = ''
    for table in result['prices'].values():
        for entry in table.values():
            for key in ('source', 'note', 'note_en'):
                if key in entry:
                    entry[key] = ''
    for entry in [result['led'], result['extras'], *result['extras']['items']]:
        for key in ('note', 'note_en'):
            if key in entry:
                entry[key] = ''
    for key, value in result['company'].items():
        if key not in ('logo_width_px', 'logo_height_px'):
            result['company'][key] = ''
    remarks = result['remark']
    for key in ('preliminary_note', 'preliminary_note_cn'):
        remarks[key] = ''
    for term in remarks.get('items', []):
        term['en'] = term['cn'] = ''
    remarks['notes'] = []
    return result


def check_or_clean(root=ROOT, clean=False):
    errors = []
    for name, transform in (('data/factory-pricing.json', public_seed),
                            ('web/demo.json', clear_amounts)):
        path = root / name
        raw = json.loads(path.read_text(encoding='utf-8'))
        sanitized = transform(raw)
        if raw == sanitized:
            continue
        if clean:
            temp = path.with_name(path.name + '.tmp')
            temp.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            os.replace(temp, path)
        else:
            errors.append(name + ': bundled price or company data is not blank')
    fixture_path = root / 'tests/fixtures.py'
    for node in ast.parse(fixture_path.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('DEMO', 'BOUNDARY') for t in node.targets):
            value = ast.literal_eval(node.value)
            if clear_amounts(value) != value:
                errors.append('tests/fixtures.py: remove fixed prices and amount-bearing notes')
    with ZipFile(root / 'templates/quotation-reference.xlsx') as workbook:
        for name in workbook.namelist():
            if name.startswith(('xl/media/', 'xl/embeddings/', 'xl/comments')):
                errors.append('Reference template contains an image, embedded file or comment')
            elif name.startswith('xl/worksheets/') and name.endswith('.xml'):
                sheet = ET.fromstring(workbook.read(name))
                for cell in sheet.findall('.//{*}c'):
                    if any(child.tag.rsplit('}', 1)[-1] in ('v', 'is', 'f') and ''.join(child.itertext()).strip() for child in cell):
                        errors.append('Reference template must contain layout only, not cell values')
            elif name == 'xl/sharedStrings.xml':
                if any((t.text or '').strip() for t in ET.fromstring(workbook.read(name)).findall('.//{*}t')):
                    errors.append('Reference template contains stored text')
            elif name in ('docProps/core.xml', 'docProps/app.xml'):
                for prop in ET.fromstring(workbook.read(name)):
                    key = prop.tag.rsplit('}', 1)[-1]
                    text = (prop.text or '').strip()
                    allowed = {'creator': 'Whole-House Customization Quotation contributors',
                               'lastModifiedBy': 'Whole-House Customization Quotation contributors',
                               'title': 'Quotation layout geometry only'}
                    if key in allowed and text not in ('', allowed[key]):
                        errors.append('Reference template contains non-public metadata')
                    elif key in ('subject', 'description', 'keywords', 'category', 'Company', 'Manager') and text:
                        errors.append('Reference template contains business metadata')
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean', action='store_true', help='Clear the public seed and example data in place')
    args = parser.parse_args()
    errors = check_or_clean(clean=args.clean)
    if errors:
        raise SystemExit('\n'.join(errors))
    print('Public price and company data are blank.')
