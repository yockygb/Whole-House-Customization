"""Bilingual display for numbered room instances."""
import json
from pathlib import Path
import unittest

from core.engine import PricingConfig


class RoomInstanceTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'data' / 'factory-pricing.json'
        self.config = PricingConfig(json.loads(path.read_text(encoding='utf-8')))

    def test_numbered_room_uses_configured_english_name(self):
        self.assertEqual(self.config.room_en('主卧1'), 'Master Bedroom 1')
        self.assertEqual(self.config.room_en('主卧 2'), 'Master Bedroom 2')

    def test_custom_room_instances_keep_custom_translation(self):
        self.config.raw['rooms'].append({'name': '影音室', 'name_en': 'Media Room'})
        self.assertEqual(self.config.room_en('影音室3'), 'Media Room 3')


if __name__ == '__main__':
    unittest.main(verbosity=2)
