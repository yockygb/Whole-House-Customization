"""Quick-entry ordering follows the saved Management catalogue order."""
import unittest
from server.catalogue import effective_rate_order, _slot_order


def sample_data():
    return {
        'categories': [{'key': 'sample', 'measure': 'area', 'pricing_model': 'projection_split'}],
        'materials': [
            {'id': 'body-a', 'part': 'body'}, {'id': 'body-b', 'part': 'body'},
            {'id': 'door-a', 'part': 'door'},
        ],
        'rates': [
            {'id': 'rate-a', 'category_key': 'sample', 'material_id': 'body-a'},
            {'id': 'rate-b', 'category_key': 'sample', 'material_id': 'body-b'},
            {'id': 'rate-door', 'category_key': 'sample', 'material_id': 'door-a'},
        ],
    }


class CatalogueOrderTests(unittest.TestCase):
    def test_library_order_is_used_when_no_category_order_exists(self):
        data = sample_data()
        orders = {'materials:body': ['body-b', 'body-a'], 'materials:door': ['door-a']}
        self.assertEqual(effective_rate_order(data, orders, {}, 'sample'),
                         ['rate-b', 'rate-a', 'rate-door'])

    def test_category_order_preserves_cross_part_slots(self):
        data = sample_data()
        orders = {'rates:sample': ['rate-door', 'rate-a', 'rate-b']}
        self.assertEqual(effective_rate_order(data, orders, {}, 'sample'),
                         ['rate-door', 'rate-a', 'rate-b'])

    def test_newer_library_order_reorders_within_category_slots(self):
        data = sample_data()
        orders = {'rates:sample': ['rate-door', 'rate-a', 'rate-b'],
                  'materials:body': ['body-b', 'body-a']}
        seqs = {'rates:sample': 1, 'materials:body': 2}
        self.assertEqual(effective_rate_order(data, orders, seqs, 'sample'),
                         ['rate-door', 'rate-b', 'rate-a'])

    def test_stale_order_ids_are_ignored(self):
        self.assertEqual(_slot_order(['old', 'rate-b'], ['rate-a', 'rate-b']),
                         ['rate-b', 'rate-a'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
