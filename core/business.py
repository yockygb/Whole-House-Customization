"""Quotation v5: explicit product models, measured add-ons and project costs.

The legacy engine remains available for quotations saved before the rebuild.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
import math
from . import engine as legacy


DEFAULT_COSTS = {'installation_per_m2': 0.0, 'volume_per_m2': .162,
                 'transport_per_m3': 0.0, 'after_sales_rate': 0.0}


def number(value, label, minimum=0):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError('Invalid number / 数值错误: ' + label)
    if not math.isfinite(n) or n < minimum:
        raise ValueError('Invalid nonnegative number / 数值须为有限非负数: ' + label)
    return n


@dataclass
class BusinessLine(legacy.LineResult):
    pricing_model: str = ''
    door_measure: float = 0
    door_factor: float = 1
    actual_projection_m2: float = 0
    estimated_volume_m3: float = 0
    extra_cost: float = 0
    cost_complete: bool = True


def line_from_dict(**data):
    cls = BusinessLine if 'actual_projection_m2' in data else legacy.LineResult
    return cls(**data)


def compute_quote(cfg, items, mode=None, discount=1, deposit_rate=.5, tax_rate=0):
    if cfg.meta.get('business_version') != 5:
        for item in items:
            view=cfg.for_category(item.cat)
            if item.door not in ('','none') or not view.is_split(item.cat):continue
            if any(e.get('charge_kind')=='upgrade' and (item.extras or {}).get(e['key'],0)>0
                   for e in view.extras_for(item.cat,item.extras)):
                raise ValueError('Upgrade requires a base door / 玻璃升级差价须先选择基础柜门')
    if cfg.meta.get('business_version') != 5 and not any(cfg.category(it.cat).get('source_key') for it in items):
        return legacy.compute_quote(cfg, items, mode, discount, deposit_rate, tax_rate)
    discount = number(discount, 'discount')
    deposit_rate = number(deposit_rate, 'deposit')
    tax_rate = number(tax_rate, 'tax')
    if discount > 1 or deposit_rate > 1:
        raise ValueError('Discount/deposit must be 0–1 / 折扣及定金比例须在0至1之间')
    policy = {k: number(cfg.raw.get('project_costs', {}).get(k, v), k)
              for k, v in DEFAULT_COSTS.items()}
    if policy['after_sales_rate'] > 1:
        raise ValueError('After-sales rate must be 0–1 / 售后比例须在0至1之间')
    lines = [compute_line(cfg, it, n + 1, mode, policy) for n, it in enumerate(items)]
    total = round(sum(l.amount for l in lines), 2)
    net = round(total * discount, 2)
    area = sum(l.actual_projection_m2 for l in lines)
    volume = area * policy['volume_per_m2']
    material = round(sum(l.supply_amount for l in lines), 2)
    installation = round(area * policy['installation_per_m2'], 2)
    transport = round(volume * policy['transport_per_m3'], 2)
    after_sales = round(net * policy['after_sales_rate'], 2)
    complete = all(l.cost_complete for l in lines)
    project_cost = round(material + installation + transport + after_sales, 2)
    summary = dict(count=len(lines), total=total, net_total=net,
                   discount=discount, discount_amount=round(total-net, 2),
                   deposit_rate=deposit_rate, deposit=round(net*deposit_rate, 2),
                   balance=round(net-round(net*deposit_rate, 2), 2),
                   tax_rate=tax_rate, tax=round(net*tax_rate, 2),
                   net_total_with_tax=round(net+round(net*tax_rate, 2), 2),
                   supply_total=material, material_cost=material,
                   actual_projection_m2=round(area, 8),
                   actual_projection_ft2=round(area/.09290304, 6),
                   estimated_volume_m3=round(volume, 8),
                   installation_cost=installation, transport_cost=transport,
                   after_sales_cost=after_sales, project_total_cost=project_cost,
                   cost_complete=complete, cost_policy=policy,
                   estimated_profit=round(net-project_cost, 2) if complete else None,
                   estimated_margin=round((net-project_cost)/net*100, 2) if complete and net else None,
                   gross_profit=round(total-material, 2),
                   gross_margin=round((total-material)/total*100, 2) if total else 0,
                   gross_profit_net=round(net-material, 2),
                   gross_margin_net=round((net-material)/net*100, 2) if net else 0,
                   led_rows=sum(l.led_amount>0 for l in lines),
                   led_total=round(sum(l.led_amount for l in lines),2),
                   extra_rows=sum(bool(l.extras_list) for l in lines),
                   extra_total=round(sum(l.extras_amount for l in lines), 2))
    summary['group_totals'] = {}
    for l in lines:
        summary['group_totals'][l.group] = round(summary['group_totals'].get(l.group, 0)+l.amount, 2)
    for key, attr in [('by_floor','floor'), ('by_room','room'), ('by_category','cat_name'), ('by_material','material_label')]:
        summary[key] = legacy._sum_by(lines, lambda l, a=attr: getattr(l, a))
    return lines, summary


def compute_line(cfg, item, idx, mode, policy):
    scoped=cfg.for_category(item.cat)
    if scoped is not cfg:return compute_line(scoped,item,idx,mode,policy)
    cat = cfg.category(item.cat)
    if cfg.meta.get('business_version') != 5:
        historical=legacy.compute_line(cfg,item,idx,mode)
        actual=item.length_mm*item.height_mm/1000000*item.qty if cat.get('cost_projection',cat['key']!='wall_panel') else 0
        complete=cfg.price_entry(item.cat,item.material).get('cost_known',True)
        if item.door not in ('','none'):complete=complete and cfg.price_entry(item.cat,item.door).get('cost_known',True)
        complete=complete and not historical.extras_list and not historical.led_amount
        return BusinessLine(**historical.to_dict(),pricing_model='historical',actual_projection_m2=actual,
                            estimated_volume_m3=actual*policy['volume_per_m2'],cost_complete=bool(complete))
    for field in ('length_mm','height_mm','depth_mm','qty'):
        number(getattr(item, field), field)
    if item.length_mm <= 0 or item.qty < 1 or item.qty != int(item.qty):
        raise ValueError('Positive length and whole quantity required / 长度须大于零且柜子数量为正整数')
    participates = cat.get('cost_projection', cat.get('key') != 'wall_panel')
    if (cat.get('measure') == 'area' or participates) and item.height_mm <= 0:
        raise ValueError('Actual height required for projection costs / 计算实际投影成本须填写柜体高度')
    if item.unit_price is not None:
        number(item.unit_price, 'unit price')
    entry = cfg.prices.get(item.cat,{}).get(item.material)
    if not entry or not entry.get('enabled',True):
        raise ValueError('Choose a material assigned to this category / 请选择该品类关联的材料')
    if entry.get('part') == 'door':
        raise ValueError('Carcass field cannot use a door / 柜体位置不可选择柜门材料')
    if item.door and item.door != 'none' and (cfg.prices.get(item.cat,{}).get(item.door,{}).get('part') != 'door' or not cfg.prices[item.cat][item.door].get('enabled',True)):
        raise ValueError('Invalid door material / 柜门材料错误')
    # Legacy base calculation is reused without its hard-coded add-on paths.
    raw = deepcopy(cfg.raw)
    raw['meta']['nonstd_factor'] = cat.get('nonstd_factor', cfg.nonstd_factor)
    raw['meta']['height_tol_ft'] = cat.get('height_tol_ft', cfg.height_tol)
    base_cfg = legacy.PricingConfig(raw, overrides=cfg.overrides)
    actual = item.length_mm * item.height_mm / 1000000 * item.qty if participates else 0
    if cat.get('pricing_model') == 'kitchen_split':
        from .kitchen import compute_base
        data = compute_base(cfg, item, idx, mode)
    else:
        base = legacy.compute_line(base_cfg, replace(item, extras={}, extras_size={},
                                   unit_price=round(item.unit_price,2) if item.unit_price is not None else None,
                                   led_type='none', led_power=False, led_sensor=False), idx, mode)
        data = base.to_dict()
    complete = entry.get('cost_known', True)
    if item.door and item.door != 'none':
        complete = complete and cfg.price_entry(item.cat, item.door).get('cost_known', True)
    extras = []
    selected = dict(item.extras or {})
    if cat.get('pricing_model') == 'kitchen_split':
        for e in cfg.extras_for(item.cat):
            if e.get('auto_with_cabinet') and e.get('enabled',True):
                selected[e['key']] = item.qty
    if item.led_type != 'none':
        if item.led_qty > 0 and not selected.get('led'):
            selected['led'] = cfg.led_to_m(item.led_qty, item.led_unit)
        for key, on in [('led_power',item.led_power),('led_sensor',item.led_sensor)]:
            if on and not selected.get(key): selected[key] = 1
    available = {e['key']: e for e in cfg.extras_for(item.cat, selected)}
    for key, quantity in selected.items():
        q = number(quantity, 'add-on quantity')
        if not q: continue
        if key not in available:
            raise ValueError('Unknown add-on / 增项不存在: ' + key)
        e = available[key]
        if not e.get('enabled',True) or (e.get('cats') and item.cat not in e['cats']):
            raise ValueError('Add-on is disabled or not assigned to this category / 增项已停用或未关联此品类: '+e.get('name',key))
        basis, unit = e.get('basis','qty'), e.get('unit','pcs').replace('²','2')
        automatic = cat.get('pricing_model') == 'kitchen_split' and e.get('auto_with_cabinet')
        size = {} if automatic else (item.extras_size or {}).get(key, {})
        measure = q
        if unit in ('pcs','set','个','套') and q != int(q):
            raise ValueError('Whole quantity required for pieces / 个或套的数量须为整数')
        if e.get('charge_kind') == 'upgrade' and cfg.is_split(item.cat) and item.door in ('','none'):
            raise ValueError('Upgrade requires a base door / 玻璃升级差价须先选择基础柜门')
        if basis == 'length':
            length = number(size.get('l_mm', item.length_mm), 'add-on length')
            if not length: raise ValueError('Positive add-on length required / 增项长度须大于零')
            measure = length / (1000 if unit == 'm' else 304.8) * q
        elif basis == 'area':
            w = number(size.get('w_mm', item.length_mm), 'add-on width')
            h = number(size.get('h_mm', item.height_mm), 'add-on height')
            if not w or not h: raise ValueError('Positive add-on dimensions required / 增项宽高须大于零')
            measure = w*h / (1000000 if unit == 'm2' else 92903.04) * q
        price = number(e.get('price',0), 'add-on retail')
        cost = e.get('cost_price')
        complete = complete and cost is not None
        cost_value = number(cost, 'add-on cost') if cost is not None else 0
        extras.append(dict(key=key, name=e.get('name',key), name_en=e.get('name_en',''),
                           basis=basis, unit=e.get('unit','pcs'), qty=q, measure=measure,
                           price=price, amount=round(measure*price,2), cost_price=cost,
                           cost_amount=round(measure*cost_value,2),
                           w_mm=size.get('w_mm',0), h_mm=size.get('h_mm',0),
                           l_mm=size.get('l_mm'), auto_with_cabinet=bool(automatic)))
    extra_amount = round(sum(e['amount'] for e in extras),2)
    extra_cost = round(sum(e['cost_amount'] for e in extras),2)
    data.update(amount=round(data['main_amount']+extra_amount,2),
                supply_amount=round(data['supply_amount']+extra_cost,2),
                extras_amount=extra_amount, extras_list=extras,
                extras_text='; '.join('%s %.4g%s = RM%.2f' % (e['name'],e['measure'],e['unit'],e['amount']) for e in extras))
    if extras: data['basis'] += ' + ' + data['extras_text']
    return BusinessLine(**data, actual_projection_m2=actual,
                        estimated_volume_m3=actual*policy['volume_per_m2'],
                        extra_cost=extra_cost, cost_complete=bool(complete))
