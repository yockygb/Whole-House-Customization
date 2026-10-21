"""Arithmetic checks use temporary unit-test values, never a bundled price list."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.engine import Item, load_config, compute_quote

class PricingTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(str(ROOT / 'data/factory-pricing.json'))
        body = self.cfg.prices['custom_cabinet']['body_particle']
        body.update(supply=1, market=[2,2])
        self.cfg.prices['custom_cabinet']['door_melamine']['market']=[3,3]
        self.cfg.prices['base_cabinet']['particle']['market']=[3,3]
        self.cfg.raw['led'].update(price_per_m=1,power_price=1,sensor_price=1)

    def calculate(self, **fields):
        data = dict(cat='custom_cabinet', material='body_particle', room='主卧',
                    length_mm=1219.2, height_mm=1219.2, depth_mm=600, qty=1,
                    extras={})
        data.update(fields)
        return compute_quote(self.cfg, [Item.from_dict(data)])

    def test_area_rate(self):
        lines, summary = self.calculate()
        self.assertEqual(lines[0].measure, 16)
        self.assertEqual(lines[0].amount, 32)  # 4 ft x 4 ft x 2
        self.assertEqual(summary['supply_total'], 16)  # 16 x 1

    def test_split_door_rate(self):
        lines, _ = self.calculate(door='door_melamine')
        self.assertEqual(lines[0].amount, 80)  # 16 x (2 + 3)

    def test_depth_factor(self):
        lines, _ = self.calculate(depth_mm=720)
        self.assertEqual(lines[0].factor, 1.2)
        self.assertEqual(lines[0].amount, 38.4)

    def test_minimum_height(self):
        lines, _ = self.calculate(height_mm=500)
        self.assertEqual(lines[0].amount, 26.4)  # 4 x 3.3 x 2

    def test_linear_foot_rate(self):
        lines, _ = self.calculate(cat='base_cabinet', material='particle',
                                  length_mm=3048, height_mm=914.4, qty=2)
        self.assertEqual(lines[0].amount, 60)  # 10 ft x 3 x 2

    def test_led_and_accessories(self):
        lines, _ = self.calculate(led_type='yes', led_qty=2, led_unit='m',
                                  led_power=True, led_sensor=True)
        self.assertEqual(lines[0].led_amount, 4)  # 2 x 1 + 1 + 1

    def test_discount_and_deposit(self):
        data = Item.from_dict(dict(cat='custom_cabinet', material='body_particle',
                                   length_mm=1219.2, height_mm=1219.2, depth_mm=600))
        _, summary = compute_quote(self.cfg, [data], discount=0.9, deposit_rate=0.3)
        self.assertEqual(summary['net_total'], 28.8)
        self.assertEqual(summary['deposit'], 8.64)

if __name__ == '__main__':
    unittest.main(verbosity=2)
