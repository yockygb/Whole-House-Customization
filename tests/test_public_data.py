"""Shipping defaults are empty; pricing still works after private configuration."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.engine import Item, PricingConfig, compute_quote, load_config
from tools.public_data import check_or_clean, clear_amounts, public_seed


class PublicDataTests(unittest.TestCase):
    def test_release_data_is_blank(self):
        self.assertEqual(check_or_clean(), [])

    def test_cleaner_erases_amounts_company_and_terms(self):
        raw = json.loads((ROOT / 'data/factory-pricing.json').read_text(encoding='utf-8'))
        raw['company'].update(name='TEST', email='test@example.invalid', logo='private.png')
        raw['prices']['custom_cabinet']['body_particle']['market'] = [1, 2]
        raw['led']['price_per_m'] = 1
        raw['remark']['items'][0]['en'] = 'TEST'
        clean = public_seed(raw)
        self.assertFalse(any(value for value in clean['company'].values() if isinstance(value, str)))
        self.assertEqual(clean['prices']['custom_cabinet']['body_particle']['market'], [0, 0])
        self.assertEqual(clean['led']['price_per_m'], 0)
        self.assertEqual(clean['remark']['items'][0]['en'], '')
        self.assertEqual(public_seed(clean), clean)

    def test_example_overrides_and_amount_descriptions_are_removed(self):
        self.assertEqual(clear_amounts({'unit_price': 1, 'note_en': 'RM1/ft'}),
                         {'unit_price': None, 'note_en': ''})

    def test_fresh_seed_has_no_amount_even_with_lighting_and_addons(self):
        cfg = load_config(str(ROOT / 'data/factory-pricing.json'))
        item = Item.from_dict(dict(cat='custom_cabinet', material='body_particle',
                                   door='door_melamine', length_mm=1219.2,
                                   height_mm=1219.2, depth_mm=600, led_type='yes',
                                   led_qty=2, led_power=True, led_sensor=True,
                                   extras={'glass_door': 1}))
        lines, summary = compute_quote(cfg, [item])
        self.assertEqual(lines[0].amount, 0)
        self.assertEqual(summary['supply_total'], 0)

    def test_missing_lighting_rates_default_to_zero(self):
        cfg = PricingConfig({})
        self.assertEqual((cfg.led_price_per_m(), cfg.led_power_price(), cfg.led_sensor_price()), (0, 0, 0))


if __name__ == '__main__':
    unittest.main(verbosity=2)
