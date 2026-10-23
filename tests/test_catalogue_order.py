"""Persistent option ordering used by the quotation manager."""
import copy
import json
from pathlib import Path
import unittest

from server.independent import reorder_catalogue


class CatalogueOrderTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'data' / 'factory-pricing.json'
        self.raw = json.loads(path.read_text(encoding='utf-8'))

    def test_categories_and_rooms_follow_saved_order(self):
        for collection, rows, field in (
                ('categories', self.raw['categories'], 'key'),
                ('rooms', self.raw['rooms'], 'name')):
            order = [row[field] for row in reversed(rows)]
            result = reorder_catalogue(copy.deepcopy(self.raw), collection, order)
            self.assertEqual([row[field] for row in result[collection]], order)

    def test_material_order_only_reorders_the_selected_part(self):
        table = self.raw['prices']['custom_cabinet']
        body = [key for key, value in table.items() if value.get('part', 'body') != 'door']
        if len(body) < 2:
            self.skipTest('Public seed has fewer than two body materials')
        order = list(reversed(body))
        result = reorder_catalogue(copy.deepcopy(self.raw), 'materials', order,
                                   category='custom_cabinet')
        ordered_body = [key for key, value in result['prices']['custom_cabinet'].items()
                        if value.get('part', 'body') != 'door']
        self.assertEqual(ordered_body, order)

    def test_order_must_contain_each_option_once(self):
        with self.assertRaises(ValueError):
            reorder_catalogue(copy.deepcopy(self.raw), 'categories', ['custom_cabinet'])
        with self.assertRaises(ValueError):
            reorder_catalogue(copy.deepcopy(self.raw), 'categories',
                              ['custom_cabinet', 'custom_cabinet'])

    def test_archived_categories_stay_outside_active_order(self):
        raw = copy.deepcopy(self.raw)
        archived = dict(raw['categories'][0], enabled=False)
        raw['categories'].append(archived)
        active_order = [row['key'] for row in reversed(raw['categories'][:-1])]
        result = reorder_catalogue(raw, 'categories', active_order)
        self.assertEqual([row['key'] for row in result['categories'][:-1]], active_order)
        self.assertEqual(result['categories'][-1], archived)


if __name__ == '__main__':
    unittest.main(verbosity=2)
