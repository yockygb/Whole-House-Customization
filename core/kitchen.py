"""Mixed kitchen units: carcass per foot (metre snapshots remain readable), doors using ordinary projection rules."""
from copy import deepcopy
from dataclasses import replace
from . import engine


def projection_rules(cfg):
    return cfg.categories.get('custom_cabinet', {})


def compute_base(cfg, item, idx, mode):
    raw = deepcopy(cfg.raw)
    cat = cfg.category(item.cat)
    raw['meta']['nonstd_factor'] = cat.get('nonstd_factor', cfg.nonstd_factor)
    raw['meta']['height_tol_ft'] = cat.get('height_tol_ft', cfg.height_tol)
    unit=cfg.price_entry(item.cat,item.material).get('unit','m')
    clean = replace(item, extras={}, extras_size={}, led_type='none',
                    led_power=False, led_sensor=False,
                    unit_price=round(item.unit_price, 8 if unit=='ft' else 2) if item.unit_price is not None else None)
    base = engine.compute_line(engine.PricingConfig(raw), replace(clean, door=''), idx, mode)
    data = base.to_dict()
    length = item.length_mm / (cfg.mm_per_ft if unit=='ft' else 1000)
    factor = cat.get('nonstd_factor',cfg.nonstd_factor) if any(f.startswith('非标') for f in base.flags) else 1
    body_price = clean.unit_price if clean.unit_price is not None else cfg.body_price(item.cat, item.material, mode)
    body_amount = round(length * factor * body_price * item.qty, 2)
    body_cost = round(length * factor * cfg.supply_price(item.cat, item.material) * item.qty, 2)
    # Kitchen doors use actual projected height; retain ordinary depth checks.
    door_raw = deepcopy(raw)
    door_cat = next(c for c in door_raw['categories'] if c['key'] == item.cat)
    ordinary = projection_rules(cfg)
    door_cat.update(measure='area', min_height_ft=0,
                    std_depth_mm=ordinary.get('std_depth_mm', 600),
                    ignore_depth=ordinary.get('ignore_depth', False))
    projected = engine.compute_line(engine.PricingConfig(door_raw), replace(clean, unit_price=None), idx, mode)
    area = item.length_mm / cfg.mm_per_ft * (max(item.height_mm / cfg.mm_per_ft, door_cat['min_height_ft'])
            if item.apply_min_height else item.height_mm / cfg.mm_per_ft)
    door_factor = max(1, item.depth_mm / door_cat['std_depth_mm']) if not door_cat['ignore_depth'] and door_cat['std_depth_mm'] else 1
    door_amount = round(area * door_factor * projected.door_price * item.qty, 2)
    door_cost = round(area * door_factor * cfg.supply_price(item.cat, item.door) * item.qty, 2) if item.door not in ('', 'none') else 0
    data.update(measure=length, unit=unit, unit_en=unit, unit_price=body_price, factor=factor,
                supply_unit=cfg.supply_price(item.cat, item.material),
                supply_amount=body_cost+door_cost, body_price=body_price, body_amount=body_amount,
                door_key=projected.door_key, door_label=projected.door_label,
                door_label_en=projected.door_label_en, door_price=projected.door_price,
                door_amount=door_amount, material_label=projected.material_label,
                material_label_en=projected.material_label_en,
                bill_h_ft=projected.bill_h_ft, min_height_applied=projected.min_height_applied,
                flags=base.flags+[f for f in projected.flags if f.startswith('按')],
                main_amount=body_amount+door_amount, amount=body_amount+door_amount,
                pricing_model='kitchen_split', door_measure=area, door_factor=door_factor,
                basis='Carcass / 柜体 %.4g%s × %.4g × RM%.2f × %d = RM%.2f; Door / 柜门 %.4gft² × %.4g × RM%.2f × %d = RM%.2f' %
                      (length, unit, factor, body_price, item.qty, body_amount, area,
                       door_factor, projected.door_price, item.qty, door_amount))
    return data
