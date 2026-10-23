"""Shared material masters with category-specific rates; SQLite is authoritative."""
import copy
import json
import sqlite3
import uuid
from core.business import DEFAULT_COSTS, number
from core.engine import PricingConfig

SCHEMA = '''
CREATE TABLE IF NOT EXISTS catalog_materials (
 id TEXT PRIMARY KEY, part TEXT NOT NULL, family TEXT NOT NULL,
 name TEXT NOT NULL, name_en TEXT NOT NULL DEFAULT '', spec TEXT NOT NULL DEFAULT '',
 enabled INTEGER NOT NULL DEFAULT 1, deleted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS catalog_rates (
 id TEXT PRIMARY KEY, category_key TEXT NOT NULL, material_id TEXT NOT NULL,
 mat_key TEXT NOT NULL, retail_price REAL NOT NULL, cost_price REAL,
 unit TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
 UNIQUE(category_key,mat_key), FOREIGN KEY(material_id) REFERENCES catalog_materials(id));
'''

CURRENT_MODELS = ('projection_split','kitchen_split','single_area')


def is_legacy_kitchen(category):
    return category.get('pricing_model') == 'linear_bundle' or (category.get('group') == 'kitchen'
            and category.get('measure') == 'length' and category.get('pricing_model') != 'kitchen_split')


def retire_legacy_bundles(conn):
    conn.execute("UPDATE catalog_rates SET enabled=0 WHERE material_id IN (SELECT id FROM catalog_materials WHERE part='bundle')")
    conn.execute("UPDATE catalog_materials SET enabled=0 WHERE part='bundle'")
    conn.execute("DELETE FROM catalog_materials WHERE part='bundle' AND NOT EXISTS (SELECT 1 FROM catalog_rates WHERE material_id=catalog_materials.id)")


def separate_kitchen_library(conn, raw):
    """Move only kitchen associations, keeping keys, prices and quote snapshots intact."""
    keys=[c['key'] for c in raw['categories'] if c.get('pricing_model')=='kitchen_split']
    if not keys:return
    marks=','.join('?' for _ in keys)
    masters=conn.execute("SELECT DISTINCT m.* FROM catalog_materials m JOIN catalog_rates r ON r.material_id=m.id WHERE m.part='body' AND r.category_key IN ("+marks+")",keys).fetchall()
    for m in masters:
        other=conn.execute('SELECT 1 FROM catalog_rates WHERE material_id=? AND category_key NOT IN ('+marks+')',(m['id'],*keys)).fetchone()
        if other:
            mid='kitchen_'+m['id']
            conn.execute("INSERT OR IGNORE INTO catalog_materials(id,part,family,name,name_en,spec,enabled,deleted) VALUES (?,'kitchen_body',?,?,?,?,?,?)",
                         (mid,m['family'],m['name'],m['name_en'],m['spec'],m['enabled'],m['deleted']))
            conn.execute('UPDATE catalog_rates SET material_id=? WHERE material_id=? AND category_key IN ('+marks+')',(mid,m['id'],*keys))
        else:conn.execute("UPDATE catalog_materials SET part='kitchen_body' WHERE id=?",(m['id'],))


def body_part(category):
    return 'kitchen_body' if category.get('pricing_model')=='kitchen_split' else 'body'


def shared_door_rates(conn):
    rates={}
    for row in conn.execute("SELECT r.* FROM catalog_rates r JOIN catalog_materials m ON m.id=r.material_id WHERE m.part='door' ORDER BY (r.category_key='custom_cabinet') DESC,r.rowid"):
        rates.setdefault(row['material_id'],dict(row))
    return rates


def migrate(conn):
    from server import store, independent
    conn.executescript(SCHEMA)
    if 'deleted' not in {r[1] for r in conn.execute('PRAGMA table_info(catalog_materials)')}:
        conn.execute('ALTER TABLE catalog_materials ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0')
    cols = {r[1] for r in conn.execute('PRAGMA table_info(quotes)')}
    if 'pricing_snapshot_json' not in cols:
        conn.execute("ALTER TABLE quotes ADD COLUMN pricing_snapshot_json TEXT")
    if conn.execute("SELECT value FROM settings WHERE key='catalogue_version'").fetchone():
        return
    raw = copy.deepcopy(store.pricing_raw())
    # Freeze old quotes before changing either calculation semantics or prices.
    legacy = store.build_config(conn)
    saved = copy.deepcopy(legacy.raw)
    for (cat,mat), value in legacy.overrides.items():
        e = saved['prices'].get(cat,{}).get(mat)
        if e is not None:
            if 'quote' in value: e['market'] = [value['quote'],value['quote']]
            if 'cost' in value: e['supply'] = value['cost']
    saved['extras']['items'] = legacy.extras_items()
    conn.execute('UPDATE quotes SET pricing_snapshot_json=? WHERE pricing_snapshot_json IS NULL',
                 (json.dumps(saved,ensure_ascii=False),))
    raw['meta'].update(business_version=5, version='5.0.0', price_mode='retail',
                       price_modes={'retail':'零售价'}, price_modes_en={'retail':'Retail price'})
    raw['project_costs'] = dict(DEFAULT_COSTS)
    raw['extras']['items'] = copy.deepcopy(legacy.extras_items())
    for e in raw['extras']['items']:
        e.setdefault('cost_price', None)
        if e['key'] == 'glass_door':
            e.update(charge_kind='upgrade', needs_review=False, enabled=True)
            e['note'] = '保留普通柜门价格；按玻璃门独立宽×高×本行总件数另计升级差价。'
            e['note_en'] = 'Upgrade differential on top of standard doors; actual glass width × height × total pieces for this line.'
    for c in raw['categories']:
        c.setdefault('pricing_model', 'linear_bundle' if c['measure']=='length' else
                     'single_area' if c['key']=='wall_panel' else 'projection_split')
        c.setdefault('cost_projection',c['key']!='wall_panel')
        c.setdefault('depth_tolerance_mm',10)
        c.setdefault('height_tol_ft',raw['meta'].get('height_tol_ft',.1))
        c.setdefault('nonstd_factor',raw['meta'].get('nonstd_factor',1.2))
        for key,e in raw['prices'].get(c['key'],{}).items():
            e['market'] = [legacy.unit_price(c['key'],key)]*2
            e['supply'] = legacy.supply_price(c['key'],key)
    sync(conn,raw)
    independent.atomic_json(store.PRICING_PATH,raw)
    store._pricing_cache['raw'] = None
    conn.execute("INSERT INTO settings(key,value) VALUES ('catalogue_version','5')")
    conn.commit()


def sync(conn, raw):
    for cat in raw['categories']:
        for key,e in raw.get('prices',{}).get(cat['key'],{}).items():
            if conn.execute('SELECT 1 FROM catalog_rates WHERE category_key=? AND mat_key=?', (cat['key'],key)).fetchone():
                continue
            part = 'bundle' if cat.get('pricing_model')=='linear_bundle' else e.get('part','body')
            mid = e.get('material_id') or part+'_'+key
            family = e.get('family') or {'body':'柜体板材','door':'柜门材料','bundle':'橱柜成品组合'}[part]
            conn.execute('INSERT OR IGNORE INTO catalog_materials(id,part,family,name,name_en,spec,enabled) VALUES (?,?,?,?,?,?,?)',
                         (mid,part,family,e.get('label',key),e.get('label_en',''),e.get('spec',''),int(e.get('enabled',True))))
            cfg = PricingConfig(raw)
            cost = e.get('supply') if e.get('cost_known',True) else None
            conn.execute('INSERT INTO catalog_rates(id,category_key,material_id,mat_key,retail_price,cost_price,unit,enabled) VALUES (?,?,?,?,?,?,?,?)',
                         (uuid.uuid4().hex,cat['key'],mid,key,cfg.default_unit_price(cat['key'],key),
                          cost,e.get('unit','ft2'),int(e.get('enabled',True))))


def apply(conn, raw):
    if raw.get('meta',{}).get('business_version') != 5: return raw
    sync(conn, raw)
    separate_kitchen_library(conn,raw)
    shared=shared_door_rates(conn)
    # Preserve configured order; values always come from category rates, never overlays.
    for c in raw['categories']:
        previous = raw['prices'].get(c['key'],{})
        out = {}
        rows = conn.execute('SELECT r.*,m.part,m.family,m.name,m.name_en,m.spec,m.enabled AS material_enabled,m.deleted FROM catalog_rates r JOIN catalog_materials m ON r.material_id=m.id WHERE r.category_key=? ORDER BY r.rowid', (c['key'],)).fetchall()
        rows = sorted(rows,key=lambda r:list(previous).index(r['mat_key']) if r['mat_key'] in previous else len(previous))
        for r in rows:
            price=shared[r['material_id']] if r['part']=='door' else r
            e = dict(previous.get(r['mat_key'],{}))
            suffix=(' / '+r['spec']) if r['spec'] else ''
            e.update(material_id=r['material_id'],label=r['name']+suffix,label_en=(r['name_en'] or r['name'])+suffix,spec=r['spec'],family=r['family'],
                     part='door' if r['part']=='door' else 'body',unit=r['unit'],
                     market=[price['retail_price']]*2,supply=price['cost_price'] or 0,
                     cost_known=price['cost_price'] is not None,
                     enabled=bool(r['enabled'] and r['material_enabled'] and not r['deleted']))
            out[r['mat_key']] = e
        raw['prices'][c['key']] = out
    return raw


def ordering_state(conn):
    """Persisted order lists plus their sequence stamps.

    Single source of truth shared by `payload()` and `api.bootstrap_payload()` so the
    Management rate table and Quick entry cannot drift apart.
    """
    orders, seqs = {}, {}
    for row in conn.execute("SELECT key,value FROM settings "
                            "WHERE key LIKE 'management_order:%' OR key LIKE 'order_seq%'"):
        name, value = row['key'], row['value']
        if name.startswith('management_order:'):
            try: orders[name[len('management_order:'):]] = json.loads(value)
            except (TypeError, ValueError): pass
        elif name.startswith('order_seq:'):
            try: seqs[name[len('order_seq:'):]] = int(value)
            except (TypeError, ValueError): pass
    return orders, seqs


def library_wins(orders, seqs, part, category_key):
    """True when this part's *stamped* library order is newer than the category rate order.

    Legacy databases carry no sequence stamps at all; they keep the original behaviour
    where a saved per-category rate order has priority. A missing/zero stamp must not
    make the two keys look "equally new" and silently switch to library order.
    """
    if not orders.get('materials:' + part):
        return False
    library = seqs.get('materials:' + part, 0)
    rate = seqs.get('rates:' + category_key, 0)
    return library > 0 and library > rate


def _slot_order(saved, available):
    """Canonical skeleton: saved ids that still exist, then the remaining ids in place."""
    base = []
    for rid in available:
        if rid and rid not in base:
            base.append(rid)
    kept = []
    for rid in saved or []:
        if rid in base and rid not in kept:
            kept.append(rid)
    return kept + [rid for rid in base if rid not in kept]


def effective_rate_order(data, orders, seqs, category):
    """Display order for one category's rate rows, using the bootstrap precedence policy.

    The skeleton is the saved `rates:<category>` list, so cross-part slots survive exactly
    as saved (a door row dragged above a body row stays there). Within one part the order
    follows that saved list until a newer stamped library order wins, in which case it
    follows `materials:<part>` — the same rule `api.bootstrap_payload()` applies to the
    body and door lists. Only when a category has no saved rate order is the skeleton
    built as body rows then door rows, each in the applicable library order.

    Every row is kept (disabled/hidden materials included) and rows that neither key
    mentions stay after the ones that do, in their original relative order.
    """
    materials = {m['id']: m for m in data['materials']}
    rates = [r for r in data['rates'] if r['category_key'] == category]
    row = next((c for c in data['categories'] if c['key'] == category), None)
    body = body_part(row) if row else 'body'
    existing = {r['id'] for r in rates}
    # Mirror bootstrap: stale ids in a saved list are ignored, and a list that resolves
    # to nothing counts as "no saved order" (fall back to the library order).
    stored = [rid for rid in (orders.get('rates:' + category) or []) if rid in existing]
    rate_rank = {rid: index for index, rid in enumerate(stored)}
    library_ranks = {part: {mid: index for index, mid in enumerate(orders.get('materials:' + part, []))}
                     for part in (body, 'door')}
    by_id = {r['id']: r for r in rates}

    def part_of(rid):
        return materials.get(by_id[rid]['material_id'], {}).get('part')

    if stored:
        skeleton = _slot_order(stored, [r['id'] for r in rates])
    else:
        # No saved order: body rows first, then the rest, each part in library order.
        skeleton = ([r['id'] for r in rates if part_of(r['id']) == body]
                    + [r['id'] for r in rates if part_of(r['id']) != body])

    out = list(skeleton)
    for part in (body, 'door'):
        slots = [index for index, rid in enumerate(out) if part_of(rid) == part]
        if not slots:
            continue
        subset = [out[index] for index in slots]
        if stored and not library_wins(orders, seqs, part, category):
            rank = {rid: rate_rank.get(rid, len(rate_rank)) for rid in subset}
        else:
            ranks = library_ranks[part]
            rank = {rid: ranks.get(by_id[rid]['material_id'], len(ranks)) for rid in subset}
        ordered = [rid for _, rid in sorted(enumerate(subset), key=lambda pair: (rank[pair[1]], pair[0]))]
        for slot, rid in zip(slots, ordered):
            out[slot] = rid
    return out


def payload(conn):
    from server import store
    categories=[c for c in store.build_config(conn).cat_list() if not is_legacy_kitchen(c) and not c.get('archived')]
    shared=shared_door_rates(conn)
    materials=[]
    for r in conn.execute("SELECT * FROM catalog_materials WHERE part IN ('body','kitchen_body','door') AND deleted=0 ORDER BY part,family,name"):
        m=dict(r)
        if m['part']=='door':m.update(retail_price=shared.get(m['id'],{}).get('retail_price'),cost_price=shared.get(m['id'],{}).get('cost_price'),unit='ft2')
        materials.append(m)
    rates=[]
    for r in conn.execute("SELECT r.*,m.part FROM catalog_rates r JOIN catalog_materials m ON m.id=r.material_id WHERE m.part IN ('body','kitchen_body','door') AND m.deleted=0 ORDER BY r.category_key,r.rowid"):
        rate=dict(r);part=rate.pop('part')
        if part=='door':rate.update(retail_price=shared[rate['material_id']]['retail_price'],cost_price=shared[rate['material_id']]['cost_price'])
        rates.append(rate)
    orders, seqs = ordering_state(conn)
    data = dict(materials=materials,rates=rates,categories=categories,orders=orders)
    # Derived, never persisted: lets Management show the same effective order Quick entry uses.
    data['rate_orders'] = {c['key']: effective_rate_order(data, orders, seqs, c['key'])
                           for c in categories}
    return data


def _write_order(conn, key, ids):
    """Persist list, global counter and per-key stamp in ONE atomic transaction.

    Two windows may save at once: a read-then-write counter (or individually
    committing setters) lets both read the same value and produce equal stamps,
    which would make a later save lose the precedence comparison. BEGIN IMMEDIATE
    plus a single UPSERT ... RETURNING increment keeps the counter strictly
    monotonic across connections, and the whole change commits or rolls back
    together.
    """
    own = not conn.in_transaction
    if own:
        conn.execute('BEGIN IMMEDIATE')
    try:
        if sqlite3.sqlite_version_info >= (3, 35, 0):
            row = conn.execute(
                "INSERT INTO settings(key,value) VALUES('order_seq','1') "
                "ON CONFLICT(key) DO UPDATE SET value=CAST(CAST(value AS INTEGER)+1 AS TEXT) "
                "RETURNING value").fetchone()
            seq = int(row[0])
        else:
            # Older SQLite without RETURNING: same transaction, still write-locked by
            # BEGIN IMMEDIATE, so the increment cannot interleave with another window.
            conn.execute("INSERT INTO settings(key,value) VALUES('order_seq','1') "
                         "ON CONFLICT(key) DO UPDATE SET value=CAST(CAST(value AS INTEGER)+1 AS TEXT)")
            seq = int(conn.execute("SELECT value FROM settings WHERE key='order_seq'").fetchone()[0])
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     ('management_order:' + key, json.dumps(ids, ensure_ascii=False)))
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     ('order_seq:' + key, str(seq)))
        # Always persist: the caller may have incidental writes open from payload()
        # (the previous setter-based implementation committed here as well).
        conn.commit()
    except Exception:
        if own:
            conn.rollback()
        raise
    return seq


def save_order(conn, key, ids):
    from server import store
    data=payload(conn)
    if key=='categories': expected=[c['key'] for c in data['categories']]
    elif key.startswith('materials:') and key.split(':',1)[1] in ('body','kitchen_body','door'):
        part=key.split(':',1)[1]
        expected=[m['id'] for m in data['materials'] if m['part']==part]
    elif key.startswith('rates:'):
        category=key.split(':',1)[1]
        if category not in {c['key'] for c in data['categories']}: raise ValueError('Category not found / 品类不存在')
        expected=[r['id'] for r in data['rates'] if r['category_key']==category and r['enabled']]
    elif key=='extras': expected=[e['key'] for e in store.build_config(conn).raw['extras']['items']]
    else: raise ValueError('Invalid list / 列表类型无效')
    ids=[str(x) for x in ids] if isinstance(ids,list) else []
    if len(ids)!=len(expected) or len(set(ids))!=len(ids) or set(ids)!=set(expected):
        raise ValueError('List changed; refresh and try again / 列表已变化，请刷新后重试')
    seq=_write_order(conn, key, ids)
    return {'ok':True,'key':key,'ids':ids,'seq':seq}



def delete_rate(conn, rid):
    from server import store
    row=conn.execute("SELECT r.*,m.part,m.enabled AS material_enabled,m.deleted FROM catalog_rates r JOIN catalog_materials m ON m.id=r.material_id WHERE r.id=?",(rid,)).fetchone()
    if not row or row['deleted']: raise ValueError('Price link not found / 价格关联不存在')
    category=store.build_config(conn).category(row['category_key'])
    if row['enabled'] and row['part']==body_part(category):
        remaining=conn.execute("SELECT 1 FROM catalog_rates r JOIN catalog_materials m ON m.id=r.material_id WHERE r.category_key=? AND r.id<>? AND r.enabled=1 AND m.enabled=1 AND m.deleted=0 AND m.part=? LIMIT 1",
                               (row['category_key'],rid,row['part'])).fetchone()
        if not remaining: raise ValueError('Keep at least one carcass material / 至少保留一种柜体材料')
    with conn: conn.execute('UPDATE catalog_rates SET enabled=0 WHERE id=?',(rid,))
    return payload(conn)


def delete_category(conn, key):
    from server import store, independent
    raw=copy.deepcopy(store.build_config(conn).raw)
    category=next((c for c in raw.get('categories',[]) if c['key']==key and not c.get('archived')),None)
    if not category: raise ValueError('Category not found / 品类不存在')
    referenced=bool(conn.execute('SELECT 1 FROM quote_items WHERE cat=? LIMIT 1',(key,)).fetchone())
    raw['categories']=[c for c in raw['categories'] if c['key']!=key]
    raw.setdefault('prices',{}).pop(key,None)
    if not referenced:
        for view in [raw,raw.get('kitchen_pricing')]:
            if not view: continue
            for extra in view.get('extras',{}).get('items',[]):
                cats=extra.get('cats')
                if cats and key in cats:
                    extra['cats']=[c for c in cats if c!=key]
                    if not extra['cats']: extra['enabled']=False
    independent.save_config(conn,raw)
    return payload(conn)


def save_material(conn, data):
    from server import store
    part = data.get('part')
    if part not in ('body','kitchen_body','door'): raise ValueError('Choose a material library / 请选择普通柜体、厨房柜体或通用柜门材料库')
    name, family = str(data.get('name','')).strip(), str(data.get('family','')).strip()
    if not name or not family: raise ValueError('Name and family required / 请填写材料名称及材料品类')
    mid = data.get('id') or uuid.uuid4().hex
    old = conn.execute('SELECT part,deleted FROM catalog_materials WHERE id=?',(mid,)).fetchone()
    if old and old['deleted']:raise ValueError('Material deleted / 材料已删除，请新增材料')
    if old and old['part'] != part: raise ValueError('Material role cannot change / 已建材料不可改变柜体或柜门用途，请新建')
    cats={c['key']:c for c in store.build_config(conn).cat_list() if not is_legacy_kitchen(c)}
    prepared=[]
    if part=='door':
        previous=shared_door_rates(conn).get(mid,{})
        price=number(data.get('retail_price',previous.get('retail_price',0)),'shared door retail')
        cost=data.get('cost_price',previous.get('cost_price'))
        cost=None if cost in (None,'') else number(cost,'shared door cost')
        for c in cats.values():
            if c.get('pricing_model') in ('projection_split','kitchen_split'):prepared.append((c,price,cost))
    elif 'rates' in data:
        seen=set()
        for rate in data['rates']:
            key=rate.get('category_key')
            if key not in cats or key in seen:raise ValueError('Invalid or duplicate material category / 材料品类关联错误或重复')
            if body_part(cats[key])!=part:raise ValueError('Wrong carcass library / 普通柜体与厨房柜体材料不可混用')
            seen.add(key)
            price=number(rate.get('retail_price'),'material retail')
            cost=rate.get('cost_price');cost=None if cost in (None,'') else number(cost,'material cost')
            prepared.append((cats[key],price,cost))
    with conn:
        conn.execute('INSERT INTO catalog_materials(id,part,family,name,name_en,spec,enabled) VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET family=excluded.family,name=excluded.name,name_en=excluded.name_en,spec=excluded.spec,enabled=excluded.enabled',
                     (mid,part,family,name,str(data.get('name_en','')).strip(),str(data.get('spec','')).strip(),int(bool(data.get('enabled',True)))))
        if part in ('body','kitchen_body') and 'rates' in data:conn.execute('UPDATE catalog_rates SET enabled=0 WHERE material_id=?',(mid,))
        if part=='door':conn.execute('UPDATE catalog_rates SET retail_price=?,cost_price=? WHERE material_id=?',(price,cost,mid))
        shared_key=next((r['mat_key'] for r in conn.execute('SELECT mat_key FROM catalog_rates WHERE material_id=? ORDER BY rowid',(mid,))),None) or 'mat_'+uuid.uuid4().hex[:12]
        for c,price,cost in prepared:
            rate=conn.execute('SELECT * FROM catalog_rates WHERE category_key=? AND material_id=? ORDER BY rowid LIMIT 1',(c['key'],mid)).fetchone()
            rid=rate['id'] if rate else uuid.uuid4().hex
            key=rate['mat_key'] if rate else shared_key
            if not rate:
                while conn.execute('SELECT 1 FROM catalog_rates WHERE category_key=? AND mat_key=?',(c['key'],key)).fetchone():
                    key='mat_'+uuid.uuid4().hex[:12]
            conn.execute('INSERT INTO catalog_rates(id,category_key,material_id,mat_key,retail_price,cost_price,unit,enabled) VALUES (?,?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET retail_price=excluded.retail_price,cost_price=excluded.cost_price,unit=excluded.unit,enabled=1',
                         (rid,c['key'],mid,key,price,cost,rate_unit(c,part)))
    return payload(conn)


def delete_material(conn, mid):
    mat=conn.execute("SELECT * FROM catalog_materials WHERE id=? AND part IN ('body','kitchen_body','door') AND deleted=0",(mid,)).fetchone()
    if not mat:raise ValueError('Material not found / 材料不存在或已删除')
    # Keep tombstones so config reseeding cannot resurrect deleted choices; quotes have snapshots.
    with conn:
        conn.execute('UPDATE catalog_rates SET enabled=0 WHERE material_id=?',(mid,))
        conn.execute('UPDATE catalog_materials SET deleted=1,enabled=0 WHERE id=?',(mid,))
    return payload(conn)


def save_rate(conn, data):
    from server import store
    cat = store.build_config(conn).category(data.get('category_key'))
    mat = conn.execute('SELECT * FROM catalog_materials WHERE id=?',(data.get('material_id'),)).fetchone()
    if not mat or mat['deleted']: raise ValueError('Material unavailable / 材料不存在或已删除')
    model = cat.get('pricing_model')
    if model not in CURRENT_MODELS:raise ValueError('Old kitchen pricing was removed / 旧版橱柜计价已移除')
    allowed = (body_part(cat),) if model=='single_area' else (body_part(cat),'door')
    if mat['part'] not in allowed: raise ValueError('Material role does not match category model / 材料用途与品类计价模型不匹配')
    unit = rate_unit(cat, mat['part'])
    price = number(data.get('retail_price'), 'retail price')
    cost = data.get('cost_price')
    cost = None if cost in (None,'') else number(cost,'cost price')
    rid = data.get('id') or uuid.uuid4().hex
    old = conn.execute('SELECT * FROM catalog_rates WHERE id=?',(rid,)).fetchone()
    if old and (old['category_key']!=cat['key'] or old['material_id']!=mat['id']):
        raise ValueError('Existing price link cannot change / 已有价格关联不可换品类或材料，请新建关联')
    key = old['mat_key'] if old else 'mat_'+uuid.uuid4().hex[:12]
    with conn:
        conn.execute('INSERT INTO catalog_rates(id,category_key,material_id,mat_key,retail_price,cost_price,unit,enabled) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET retail_price=excluded.retail_price,cost_price=excluded.cost_price,unit=excluded.unit,enabled=excluded.enabled',
                    (rid,cat['key'],mat['id'],key,price,cost,unit,int(bool(data.get('enabled',True)))))
        if mat['part']=='door':conn.execute('UPDATE catalog_rates SET retail_price=?,cost_price=? WHERE material_id=?',(price,cost,mat['id']))
    return payload(conn)


def save_category(conn, data):
    """Save the category AND both material association lists as one operation."""
    from server import store, independent
    raw = copy.deepcopy(store.build_config(conn).raw)
    category = dict(data.get('category') or {})
    key = category.get('key') or 'category_'+uuid.uuid4().hex[:12]
    model = category.get('pricing_model')
    if model not in CURRENT_MODELS:
        raise ValueError('Select a pricing model / 请选择计价模型')
    name = str(category.get('name','')).strip()
    if not name: raise ValueError('Category name required / 请填写品类名称')
    category.update(key=key,name=name,name_en=category.get('name_en') or name,
                    measure='length' if model=='kitchen_split' else 'area',
                    group='kitchen' if model=='kitchen_split' else 'cabinet')
    if model=='kitchen_split':category['body_unit']='ft'
    allowed=(body_part(category),) if model=='single_area' else (body_part(category),'door')
    prepared=[];seen=set()
    bindings=list(data.get('bindings',[]))
    shared=shared_door_rates(conn)
    if model in ('projection_split','kitchen_split'):
        bound={b.get('material_id') for b in bindings}
        for mat in conn.execute("SELECT id FROM catalog_materials WHERE part='door' AND enabled=1 AND deleted=0"):
            if mat['id'] not in bound and mat['id'] in shared:bindings.append(dict(material_id=mat['id'],**{k:shared[mat['id']][k] for k in ('retail_price','cost_price')}))
    for binding in bindings:
        mid=binding.get('material_id')
        if mid in seen:raise ValueError('Duplicate material link / 材料不可重复关联')
        seen.add(mid)
        mat=conn.execute('SELECT * FROM catalog_materials WHERE id=?',(mid,)).fetchone()
        if not mat or mat['part'] not in allowed or not mat['enabled'] or mat['deleted']:
            raise ValueError('Material does not match category model or is disabled / 关联材料用途不符或已停用')
        source=shared[mid] if mat['part']=='door' and mid in shared else binding
        price=number(source.get('retail_price'),'retail price')
        cost=source.get('cost_price')
        cost=None if cost in (None,'') else number(cost,'cost price')
        old=conn.execute('SELECT * FROM catalog_rates WHERE category_key=? AND material_id=? ORDER BY rowid LIMIT 1',(key,mid)).fetchone()
        prepared.append((dict(mat),old,price,cost))
    if not any(m['part']==body_part(category) for m,_,_,_ in prepared):
        raise ValueError('Link at least one carcass material / 请至少关联一种柜体材料')
    index=next((i for i,c in enumerate(raw['categories']) if c['key']==key),None)
    if index is None:raw['categories'].append(category)
    else:raw['categories'][index]=category
    table={k:dict(v,enabled=False) for k,v in raw['prices'].get(key,{}).items()}
    records=[]
    for mat,old,price,cost in prepared:
        unit=rate_unit(category,mat['part'])
        mat_key=old['mat_key'] if old else shared[mat['id']]['mat_key'] if mat['part']=='door' and mat['id'] in shared else 'mat_'+uuid.uuid4().hex[:12]
        rid=old['id'] if old else uuid.uuid4().hex
        table[mat_key]=dict(material_id=mat['id'],label=mat['name'],label_en=mat['name_en'],part='door' if mat['part']=='door' else 'body',
                            unit=unit,supply=cost or 0,market=[price,price],enabled=True)
        records.append((rid,key,mat['id'],mat_key,price,cost,unit))
    raw['prices'][key]=table
    independent.validate_config(raw)
    previous=copy.deepcopy(store.pricing_raw())
    # All input checks happen before touching either store; restore the config if SQL fails.
    with independent.GUARD:
        try:
            with conn:
                conn.execute('UPDATE catalog_rates SET enabled=0 WHERE category_key=?',(key,))
                for record in records:
                    conn.execute('INSERT INTO catalog_rates(id,category_key,material_id,mat_key,retail_price,cost_price,unit,enabled) VALUES (?,?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET retail_price=excluded.retail_price,cost_price=excluded.cost_price,unit=excluded.unit,enabled=1',record)
                independent.atomic_json(store.PRICING_PATH,raw)
        except Exception:
            independent.atomic_json(store.PRICING_PATH,previous)
            raise
        finally:store._pricing_cache['raw']=None
    return payload(conn)


def rate_unit(category, part):
    if category.get('pricing_model') == 'kitchen_split':
        return 'ft2' if part == 'door' else category.get('body_unit','ft')
    return 'ft' if category['measure']=='length' else 'pcs' if category['measure']=='pcs' else 'ft2'


def migrate_kitchen(conn):
    """One in-place update; old quotation snapshots retain the finished-bundle model."""
    from server import store, independent
    if store.pricing_raw().get('meta',{}).get('kitchen_pricing_version') == 1:
        return
    raw=copy.deepcopy(store.build_config(conn).raw)
    old=copy.deepcopy(store.pricing_raw())
    pinned=json.dumps(raw,ensure_ascii=False)
    with independent.GUARD:
        try:
            with conn:
                conn.execute('UPDATE quotes SET pricing_snapshot_json=? WHERE pricing_snapshot_json IS NULL',(pinned,))
                for key,prices in [('base_cabinet',(0,0)),('wall_cabinet',(0,0))]:
                    cat=next((c for c in raw['categories'] if c['key']==key),None)
                    if not cat:continue
                    cat.update(pricing_model='kitchen_split',measure='length',group='kitchen')
                    if key=='wall_cabinet':cat.update(default_height_mm=800,std_height_ft=800/raw['meta'].get('mm_per_ft',304.8))
                    # Reuse shared carcass masters, but not the old bundled-door costs.
                    for mat_key,source,price in zip(('particle','plywood'),('body_particle','body_plywood'),prices):
                        raw['prices'].setdefault(key,{}).setdefault(mat_key,{}).update(
                            note='柜体按米计价，不含柜门与石材；'+('吊柜标准高度800mm。' if key=='wall_cabinet' else '地柜脚线另计，拉手选配。'),
                            note_en='Carcass per metre, doors and stone excluded; '+('wall standard height 800 mm.' if key=='wall_cabinet' else 'plinth charged separately; handle optional.'))
                        master=conn.execute('SELECT material_id FROM catalog_rates WHERE category_key=? AND mat_key=?',('custom_cabinet',source)).fetchone()
                        if not master:raise ValueError('Missing ordinary carcass master / 缺少普通柜体材料')
                        conn.execute('INSERT INTO catalog_rates(id,category_key,material_id,mat_key,retail_price,cost_price,unit,enabled) VALUES (?,?,?,?,?,NULL,?,1) ON CONFLICT(category_key,mat_key) DO UPDATE SET material_id=excluded.material_id,retail_price=excluded.retail_price,cost_price=NULL,unit=excluded.unit,enabled=1',
                                     (uuid.uuid4().hex,key,master['material_id'],mat_key,price,'m'))
                    doors=conn.execute("SELECT r.* FROM catalog_rates r JOIN catalog_materials m ON m.id=r.material_id WHERE r.category_key='custom_cabinet' AND m.part='door' AND r.enabled=1 AND m.enabled=1").fetchall()
                    for d in doors:
                        conn.execute('INSERT OR IGNORE INTO catalog_rates(id,category_key,material_id,mat_key,retail_price,cost_price,unit,enabled) VALUES (?,?,?,?,?,?,?,1)',
                                     (uuid.uuid4().hex,key,d['material_id'],d['mat_key'],d['retail_price'],d['cost_price'],'ft2'))
                extras=raw['extras']['items']
                for e in [dict(key='kitchen_plinth',name='橱柜脚线',name_en='Kitchen Plinth',price=0,cost_price=None,unit='m',basis='length',cats=['base_cabinet'],enabled=True,auto_with_cabinet=True),
                          dict(key='kitchen_handle',name='地柜铝合金免拉手（选配）',name_en='Optional Aluminium Handle Profile',price=0,cost_price=None,unit='m',basis='qty',cats=['base_cabinet'],enabled=True)]:
                    if not any(x['key']==e['key'] for x in extras):extras.append(e)
                raw['meta'].update(kitchen_pricing_version=1,version='5.1.0')
                raw=apply(conn,raw)
                independent.validate_config(raw)
                independent.atomic_json(store.PRICING_PATH,raw)
        except Exception:
            independent.atomic_json(store.PRICING_PATH,old)
            raise
        finally:store._pricing_cache['raw']=None


def convert_kitchen_to_feet(conn, raw):
    """Equivalent rate conversion only; never rewrite existing quotation snapshots."""
    from core.config import APP_VERSION
    keys=[c['key'] for c in raw['categories'] if c.get('pricing_model')=='kitchen_split']
    factor=raw['meta'].get('mm_per_ft',304.8)/1000
    rows=[]
    if keys:
        marks=','.join('?' for _ in keys)
        rows=conn.execute("SELECT r.* FROM catalog_rates r JOIN catalog_materials m ON m.id=r.material_id WHERE m.part IN ('body','kitchen_body') AND r.unit='m' AND r.category_key IN ("+marks+")",keys).fetchall()
    changed=bool(rows) or raw['meta'].get('version')!=APP_VERSION or raw['meta'].get('kitchen_length_unit')!='ft' or any(c.get('body_unit')!='ft' for c in raw['categories'] if c['key'] in keys)
    if not changed:return False
    if rows:conn.execute('UPDATE quotes SET pricing_snapshot_json=? WHERE pricing_snapshot_json IS NULL',(json.dumps(raw,ensure_ascii=False),))
    for row in rows:
        conn.execute("UPDATE catalog_rates SET retail_price=?,cost_price=?,unit='ft' WHERE id=?",
                     (round(row['retail_price']*factor,8),None if row['cost_price'] is None else round(row['cost_price']*factor,8),row['id']))
    for c in raw['categories']:
        if c['key'] not in keys:continue
        c['body_unit']='ft'
        for e in raw['prices'].get(c['key'],{}).values():
            if e.get('part')=='door' or e.get('unit')!='m':continue
            e.update(unit='ft',market=[round(p*factor,8) for p in e['market']],supply=round(e.get('supply',0)*factor,8))
            if 'note' in e:e['note']=e['note'].replace('柜体按米计价','柜体按英尺(FT)计价')
            if 'note_en' in e:e['note_en']=e['note_en'].replace('Carcass per metre','Carcass per foot (FT)')
    raw['meta'].update(kitchen_length_unit='ft',version=APP_VERSION)
    return True


def migrate_kitchen_feet(conn):
    from server import store,independent
    previous=copy.deepcopy(store.pricing_raw())
    raw=copy.deepcopy(store.build_config(conn).raw)
    with independent.GUARD:
        try:
            with conn:
                if convert_kitchen_to_feet(conn,raw):independent.atomic_json(store.PRICING_PATH,raw)
        except Exception:
            independent.atomic_json(store.PRICING_PATH,previous)
            raise
        finally:store._pricing_cache['raw']=None


def extend_historical_kitchen(raw, current):
    """New kitchen choices have separate keys; historical category keys keep their meaning."""
    known={c['key']:c for c in raw['categories']}
    candidates=[c for c in current['categories'] if c.get('pricing_model')=='kitchen_split'
                and (c['key'] not in known or is_legacy_kitchen(known[c['key']]))]
    if not candidates and not raw.get('kitchen_pricing'):return raw
    raw=copy.deepcopy(raw)
    if not raw.get('kitchen_pricing'):
        scoped=copy.deepcopy(current)
        aliases={c['key']:'current_'+c['key'] for c in candidates}
        for cat in scoped['categories']:
            key=cat['key']
            if key in aliases:
                cat.update(key=aliases[key],source_key=key)
                scoped['prices'][aliases[key]]=scoped['prices'].pop(key)
        for extra in scoped['extras']['items']:
            if extra.get('cats'):extra['cats']=[aliases.get(key,key) for key in extra['cats']]
        raw['kitchen_pricing']=scoped
    for cat in raw['kitchen_pricing']['categories']:
        if not cat.get('source_key'):continue
        table=raw['kitchen_pricing']['prices'][cat['key']]
        for key,entry in current['prices'].get(cat['source_key'],{}).items():
            if key not in table:table[key]=copy.deepcopy(entry)
        if cat['key'] not in known:raw['categories'].append(copy.deepcopy(cat))
        outer=raw['prices'].setdefault(cat['key'],{})
        for key,entry in table.items():
            if key not in outer:outer[key]=copy.deepcopy(entry)
    return raw


def include_glass_option(raw, current, items):
    """Refresh an unused glass option, never the price of an already quoted glass door."""
    glass=next((e for e in current['extras']['items'] if e['key']=='glass_door'),None)
    if glass is None:return raw
    raw=copy.deepcopy(raw)
    aliases={c['key'] for c in raw['categories'] if c.get('source_key')}
    views=[(raw,[i for i in items if i['cat'] not in aliases])]
    if raw.get('kitchen_pricing'):views.append((raw['kitchen_pricing'],[i for i in items if i['cat'] in aliases]))
    for view,selected in views:
        if any((i.get('extras') or {}).get('glass_door',0)>0 for i in selected):continue
        extras=view['extras']['items']
        old=next((e for e in extras if e['key']=='glass_door'),None)
        replacement=copy.deepcopy(glass)
        if old and old.get('enabled',True) and not old.get('needs_review'):
            replacement['price']=old['price']
            replacement['cost_price']=old.get('cost_price')
        names={c.get('source_key',c['key']):c['key'] for c in view['categories']}
        replacement['cats']=[names.get(key,key) for key in glass.get('cats',[])]
        if old is None:extras.append(replacement)
        else:extras[extras.index(old)]=replacement
    return raw
