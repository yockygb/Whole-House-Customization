"""Consistent English-first and Chinese-second generated quotation remarks."""
from __future__ import annotations
import re

DEFAULT_NAMES = {
    'led': ('LED Strip', '灯带'),
    'led_power': ('LED Power Supply', '灯带电源'),
    'led_sensor': ('Receiver + Sensor', '接收器 + 感应器'),
    'glass_door': ('Glass Door', '玻璃门'),
    'quartz': ('Quartz Countertop', '石英石台面'),
    'sink': ('Sink', '水槽'),
    'pull_down': ('Pull-down Rack', '下拉架'),
    'tall_basket': ('Tall Cabinet Pull-out Basket', '高柜联动拉篮'),
    'dish_basket': ('Dish Basket', '碗碟拉篮'),
}
UNITS = {'m': ('m', '米'), 'ft': ('ft', '英尺'),
         'mm': ('mm', '毫米'), 'cm': ('cm', '厘米'),
         'set': ('set', '套'), 'sets': ('sets', '套')}

def _number(value):
    return format(float(value or 0), '.8g')

def _unit(unit):
    unit=str(unit or '').strip()
    return UNITS.get(unit, (unit, unit))

def _names(entry, catalogue):
    key=entry.get('key', '')
    configured=catalogue.get(key, {})
    default_en,default_cn=DEFAULT_NAMES.get(key, ('English name required: '+key, key))
    en=entry.get('name_en') or configured.get('name_en') or default_en
    cn=entry.get('name') or configured.get('name') or default_cn
    return str(en),str(cn)

def remark(ln, cfg):
    """Return bilingual result-only remarks, without exposing price arithmetic."""
    en=[];cn=[]
    if getattr(ln,'pricing_model','')=='kitchen_split':
        unit_en,unit_cn=_unit(ln.unit)
        en.append('Carcass %s %s' % (_number(ln.measure),unit_en))
        cn.append('柜体%s%s' % (_number(ln.measure),unit_cn))
        if getattr(ln,'door_key',''):
            en.append('Door %s ft²' % _number(ln.door_measure))
            cn.append('柜门%s平方英尺' % _number(ln.door_measure))
    led=cfg.led_meta()
    selected_led=(getattr(ln, 'led_type', 'none') not in ('none', '', None)
                  and (float(getattr(ln, 'led_qty', 0) or 0)>0
                       or bool(getattr(ln, 'led_power', False))
                       or bool(getattr(ln, 'led_sensor', False))))
    if selected_led or float(getattr(ln, 'led_amount', 0) or 0)>0:
        unit_en,unit_cn=_unit(getattr(ln, 'led_unit', 'm') or 'm')
        quantity=_number(getattr(ln, 'led_qty', 0))
        en.append(f"{led.get('label_en') or 'LED Strip'} {quantity} {unit_en}")
        cn.append(f"{led.get('label') or '灯带'} {quantity} {unit_cn}")
        if getattr(ln, 'led_power', False):
            en.append((led.get('power_label_en') or 'Power Supply')+' × 1')
            cn.append((led.get('power_label') or '电源')+' × 1')
        if getattr(ln, 'led_sensor', False):
            en.append((led.get('sensor_label_en') or 'Receiver + Sensor')+' × 1')
            cn.append((led.get('sensor_label') or '接收器 + 感应器')+' × 1')

    catalogue={e.get('key'):e for e in cfg.extras_items()}
    for entry in getattr(ln, 'extras_list', []) or []:
        en_name,cn_name=_names(entry,catalogue)
        basis=entry.get('basis','qty')
        if cfg.meta.get('business_version')==5 or getattr(ln,'pricing_model','')=='kitchen_split':
            quantity=_number(entry.get('measure',entry.get('qty',1)))
            unit=entry.get('unit','pcs')
            if basis=='length' and entry.get('l_mm'):
                length=_number(entry['l_mm'])
                en_name+=f' {length} mm';cn_name+=f' {length} 毫米'
            elif basis=='area' and entry.get('w_mm') and entry.get('h_mm'):
                width,height=_number(entry['w_mm']),_number(entry['h_mm'])
                en_name+=f' {width} × {height} mm';cn_name+=f' {width} × {height} 毫米'
            en_name+=f' {quantity} {unit}'
            cn_name+=f' {quantity} {unit}'
        elif basis=='length':
            measure=f"{float(entry.get('measure',0) or 0):.2f}"
            length=float(entry.get('l_mm') or 0)
            if length>0:
                quantity=entry.get('qty',1)
                count=f' × {_number(quantity)}' if quantity!=1 else ''
                en_name+=f' {_number(length)} mm{count} ({measure} ft)'
                cn_name+=f' {_number(length)} 毫米{count}（{measure} 英尺）'
            else:
                en_name+=f' {measure} ft';cn_name+=f' {measure} 英尺'
        elif basis=='area':
            w=float(entry.get('w_mm') or 0);h=float(entry.get('h_mm') or 0)
            if w>0 and h>0:
                en_name+=f' {_number(w)} × {_number(h)} mm'
                cn_name+=f' {_number(w)} × {_number(h)} 毫米'
            measure=f"{float(entry.get('measure',0) or 0):.2f}"
            en_name+=f' ({measure} ft²)';cn_name+=f'（{measure} 平方英尺）'
        else:
            quantity=_number(entry.get('qty',1))
            unit=entry.get('unit') or catalogue.get(entry.get('key'),{}).get('unit','')
            if unit in ('m','ft','cm','mm'):
                u_en,u_cn=_unit(unit)
                en_name+=f' {quantity} {u_en}';cn_name+=f' {quantity} {u_cn}'
            else:
                en_name+=f' × {quantity}';cn_name+=f' × {quantity}'
        en.append(en_name);cn.append(cn_name)

    # User-authored notes retain their independently entered languages.
    if getattr(ln,'item_note_en',''):en.append(ln.item_note_en)
    if getattr(ln,'item_note',''):cn.append(ln.item_note)
    for flag in getattr(ln,'flags',[]) or []:
        translated={'手动定价':'Manual unit price','参考价':'Reference price'}.get(flag)
        if translated is None:
            if flag.startswith('超深'):translated=flag.replace('超深','Depth factor ',1)
            elif flag.startswith('非标'):translated=flag.replace('非标','Non-standard ',1)
            else:
                minimum=re.fullmatch(r'按(.+ft)起算',flag)
                if minimum:translated='Minimum billable height '+minimum.group(1)
        if translated:en.append(translated)
        cn.append(flag)
    return ('Incl. '+', '.join(en) if en else '', '含 '+ '，'.join(cn) if cn else '')
