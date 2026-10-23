"""Editable configuration, backups and local-only application services."""
from __future__ import annotations
import base64, copy, io, json, math, os, re, sqlite3, threading, time
from datetime import datetime
from pathlib import Path
from core.config import APP_ID, APP_VERSION, BASE_DIR, DATA_DIR, DB_PATH, PRICING_PATH, EXPORT_DIR
from core.engine import PricingConfig
from server import store

GUARD = threading.RLock()
TABLES = ('catalog_materials','catalog_rates','customers','projects','quotes','quote_items','materials','price_versions',
          'suppliers','custom_extras','custom_floors','settings','attachments')

def atomic_json(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.flush(); os.fsync(f.fileno())
    for attempt in range(5):
        try:
            os.replace(tmp,path)
            break
        except PermissionError:
            if attempt==4: raise
            time.sleep(.05)

def validate_config(raw):
    from server.catalogue import is_legacy_kitchen
    if not isinstance(raw,dict): raise ValueError('Invalid configuration / 配置格式错误')
    for name in ('meta','prices','company','extras'):
        if not isinstance(raw.get(name),dict): raise ValueError('Missing section / 缺少配置分区: '+name)
    if not raw.get('categories'): raise ValueError('At least one category / 至少保留一个品类')
    if not any(c.get('enabled',True) for c in raw['categories']):raise ValueError('At least one enabled category / 至少保留一个启用品类')
    if not raw.get('rooms'):raise ValueError('At least one room / 至少保留一个区域')
    keys=set()
    for c in raw['categories']:
        if is_legacy_kitchen(c):raise ValueError('Old kitchen pricing was removed; use carcass per metre plus projected doors / 旧版橱柜计价已移除，请使用柜体按米＋柜门投影')
        key=c.get('key','')
        if not re.fullmatch(r'[a-z][a-z0-9_]*',key) or key in keys:
            raise ValueError('Unique English category key required / 品类编码须为唯一英文编码')
        keys.add(key)
        if c.get('group') not in {g['key'] for g in raw.get('groups',[])}:
            raise ValueError('Unknown category group / 品类体系不存在')
        if c.get('measure') not in ('area','length','pcs'): raise ValueError('Invalid measure / 计价方式错误')
        for k in ('std_depth_mm','min_height_ft','default_height_mm','std_height_ft'):
            if k in c and (not math.isfinite(float(c[k])) or float(c[k])<0): raise ValueError('Invalid rule / 计价参数错误: '+k)
        if not raw['prices'].get(key): raise ValueError('Each category needs a material / 每个品类至少需要一种材料')
    def check(value):
        if isinstance(value,float) and not math.isfinite(value): raise ValueError('Finite values required / 数值必须有限')
        if isinstance(value,dict):
            for k,v in value.items():
                if k in ('price','supply','unit_price','quote','price_per_m','power_price','sensor_price') and isinstance(v,(int,float)) and v<0:
                    raise ValueError('Nonnegative price required / 价格不可为负数')
                check(v)
        if isinstance(value,list):
            for x in value: check(x)
    check(raw)
    from core.business import DEFAULT_COSTS, number
    for k,v in raw.get("project_costs",{}).items():
        if k in DEFAULT_COSTS: number(v,k)
    if float(raw.get("project_costs",{}).get("after_sales_rate",.05))>1: raise ValueError("After-sales rate must be 0–1 / 售后比例须在0至1之间")
    for e in raw.get("extras",{}).get("items",[]):
        if e.get('auto_with_cabinet') and (e.get('basis')!='length' or e.get('unit') not in ('m','ft')):
            raise ValueError('Automatic kitchen extras require length basis in metres / 橱柜自动增项须按米计长度')
        if e.get("cost_price") is not None: number(e["cost_price"],"add-on cost")
        unit=e.get("unit","pcs").replace("²","2")
        allowed={"qty":("pcs","set","个","套","m","ft","m2","ft2"),"length":("m","ft"),"area":("m2","ft2")}
        if unit not in allowed.get(e.get("basis","qty"),()): raise ValueError("Add-on unit does not match basis / 增项单位与计价依据不匹配")
    for c in raw["categories"]:
        for k in ("depth_tolerance_mm","height_tol_ft","nonstd_factor"):
            if k in c: number(c[k],k)
        if float(c.get("nonstd_factor",1.2))<=0: raise ValueError("Factor must be positive / 系数须大于零")
    if float(raw['meta'].get('mm_per_ft',304.8))<=0 or float(raw['meta'].get('nonstd_factor',1.2))<=0:
        raise ValueError('Conversion and factors must be positive / 换算率和系数须大于零')
    if float(raw.get('led',{}).get('price_per_m',0))<0:
        raise ValueError('LED rate must be nonnegative / 灯带单价不可为负数')
    for e in raw.get('extras',{}).get('items',[]):
        if e.get('basis','qty') not in ('qty','area','length'):raise ValueError('Invalid add-on basis / 增项依据错误')
        if any(k not in keys for k in e.get('cats',[])):raise ValueError('Unknown add-on category / 增项适用品类不存在')
    co=raw['company']
    logo=co.get('logo','')
    if logo and (os.path.isabs(logo) or '..' in Path(logo).parts):
        raise ValueError('Use the logo upload button / 请使用Logo上传按钮')
    return raw

def save_config(conn, raw):
    previous=store.pricing_raw()
    # Removed catalogue entries referenced by existing quotes remain as inactive archive entries.
    referenced={(r[0],r[1],r[2]) for r in conn.execute('SELECT DISTINCT cat,material,door FROM quote_items')}
    for old in previous.get('categories',[]):
        key=old['key']
        if any(c==key for c,_,_ in referenced):
            if not any(c['key']==key for c in raw.get('categories',[])):
                raw.setdefault('categories',[]).append(dict(old,enabled=False,archived=True))
            table=raw.setdefault('prices',{}).setdefault(key,{})
            for c,mat,door in referenced:
                if c!=key:continue
                for k in (mat,door):
                    if k and k not in table and k in previous.get('prices',{}).get(key,{}):table[k]=dict(previous['prices'][key][k],enabled=False)
    validate_config(raw)
    with GUARD:
        # Retain an independent rollback point before replacing an editable configuration.
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        atomic_json(Path(DATA_DIR)/'config-history'/(stamp+'.json'),store.pricing_raw())
        previous=store.pricing_raw()
        for row in conn.execute('SELECT * FROM materials'):
            entry=raw.get('prices',{}).get(row['cat_key'],{}).get(row['mat_key'])
            old=previous.get('prices',{}).get(row['cat_key'],{}).get(row['mat_key'],{})
            if entry:
                if entry.get('label') != old.get('label') or entry.get('label_en') != old.get('label_en'):
                    conn.execute('UPDATE materials SET name=?,name_en=? WHERE id=?',(entry.get('label',''),entry.get('label_en',''),row['id']))
                if 'enabled' in entry and entry.get('enabled')!=old.get('enabled'):
                    conn.execute('UPDATE materials SET enabled=? WHERE id=?',(int(bool(entry['enabled'])),row['id']))
        atomic_json(PRICING_PATH,raw)
        store._pricing_cache['raw']=None
        store.seed_materials(conn)

def export_config(conn,quote):
    snapshot=quote.get('snapshot') or {}
    if quote.get('locked') and snapshot.get('pricing'):
        overrides={(e['cat'],e['mat']):{k:v for k,v in e.items() if k in ('quote','cost')} for e in snapshot.get('overrides',[])}
        return PricingConfig(snapshot['pricing'],overrides=overrides)
    return store.config_for(conn,quote)

def backup_payload(conn):
    return {'format':'VOUGUER-Backup','version':1,'at':store.now(),
            'pricing':store.pricing_raw(),
            'tables':{t:[dict(r) for r in conn.execute('SELECT * FROM '+t)] for t in TABLES},
            'logo':base64.b64encode((Path(DATA_DIR)/'company-logo.png').read_bytes()).decode() if (Path(DATA_DIR)/'company-logo.png').exists() else None}

def install(api):
    def route(method,path):
        def wrap(fn):
            api.ROUTES.insert(0,(method,re.compile('^'+path+'$'),fn.__name__))
            setattr(api,fn.__name__,fn)
            return fn
        return wrap
    store.export_config=export_config

    @route('GET','/api/identity')
    def independent_identity(conn,m,body,q):
        return {'application':APP_ID,'version':APP_VERSION,'data_directory':DATA_DIR}

    @route('GET','/api/config')
    def independent_config_get(conn,m,body,q):
        return {'config':copy.deepcopy(store.build_config(conn).raw)}

    @route('PUT','/api/config')
    def independent_config_put(conn,m,body,q):
        try:
            save_config(conn,body['config'])
            return {'ok':True,'bootstrap':api.bootstrap_payload(conn)}
        except (ValueError,KeyError,TypeError) as e: raise api.ApiError(str(e))

    @route('POST','/api/materials')
    def independent_material_new(conn,m,body,q):
        raw=copy.deepcopy(store.pricing_raw())
        cat=body.get('cat_key'); key=body.get('mat_key') or 'mat_'+str(time.time_ns())
        if cat not in raw['prices']: raise api.ApiError('Choose a category / 请选择品类')
        if key in raw['prices'][cat]: raise api.ApiError('Material key exists / 材料编码已存在')
        price=float(body.get('quote_price') or 0); cost=float(body.get('cost_price') or 0)
        raw['prices'][cat][key]={'label':body.get('name',''),'label_en':body.get('name_en',''),
                               'part':body.get('part','body'),'unit':body.get('unit','ft2'),
                               'supply':cost,'market':[price,price]}
        save_config(conn,raw)
        row=conn.execute('SELECT id FROM materials WHERE cat_key=? AND mat_key=?',(cat,key)).fetchone()
        return {'ok':True,'material':store.update_material(conn,row['id'],body)}

    @route('DELETE',r'/api/materials/(\d+)')
    def independent_material_disable(conn,m,body,q):
        return {'ok':True,'material':store.update_material(conn,int(m.group(1)),{'enabled':False})}

    @route('POST','/api/logo')
    def independent_logo(conn,m,body,q):
        from PIL import Image
        data=base64.b64decode(body.get('data','').split(',')[-1],validate=True)
        if len(data)>5_000_000:raise api.ApiError('Logo limit 5 MB / Logo限5MB')
        try:
            im=Image.open(io.BytesIO(data)).convert('RGBA');im.thumbnail((1400,600))
            dest=Path(DATA_DIR)/'company-logo.png';temp=dest.with_suffix('.tmp')
            im.save(temp,format='PNG');os.replace(temp,dest)
        except Exception:raise api.ApiError('Invalid image / 图片格式错误')
        raw=copy.deepcopy(store.pricing_raw());raw['company']['logo']='data/company-logo.png'
        # Resolve uploads using DATA_DIR when a separate data directory is configured.
        save_config(conn,raw)
        return {'ok':True}

    @route('GET','/api/backup')
    def independent_backup(conn,m,body,q):
        name='Quotation-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json'
        path=Path(EXPORT_DIR)/name;atomic_json(path,backup_payload(conn))
        return {'__file__':str(path),'__name__':name}

    @route('POST','/api/restore')
    def independent_restore(conn,m,body,q):
        if body.get('format')!='VOUGUER-Backup' or body.get('version')!=1:raise api.ApiError('Invalid backup / 备份格式错误')
        logo=None
        try:
            validate_config(body['pricing'])
            tables=body['tables']
            for table in TABLES:
                if not isinstance(tables.get(table),list) or not all(isinstance(row,dict) and row for row in tables[table]):
                    raise ValueError('Missing or invalid backup table / 备份数据表缺失或格式错误: '+table)
            if body.get('logo') is not None:
                from PIL import Image
                logo=base64.b64decode(body['logo'],validate=True)
                if len(logo)>5_000_000:raise ValueError('Logo limit 5 MB / Logo限5MB')
                with Image.open(io.BytesIO(logo)) as im:im.verify()
        except Exception as e:raise api.ApiError(str(e))
        with GUARD:
            before=backup_payload(conn)
            atomic_json(Path(DATA_DIR)/'restore-backups'/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json'),before)
            logo_path=Path(DATA_DIR)/'company-logo.png'
            previous_logo=logo_path.read_bytes() if logo_path.exists() else None
            def replace_logo(data):
                if data is None:
                    logo_path.unlink(missing_ok=True)
                else:
                    tmp=logo_path.with_suffix('.tmp')
                    tmp.write_bytes(data);os.replace(tmp,logo_path)
            try:
                conn.execute('BEGIN')
                for table in reversed(TABLES): conn.execute('DELETE FROM '+table)
                for table in TABLES:
                    columns={r[1] for r in conn.execute('PRAGMA table_info('+table+')')}
                    for row in body.get('tables',{}).get(table,[]):
                        row={k:v for k,v in row.items() if k in columns}
                        conn.execute('INSERT INTO '+table+'('+','.join('"'+k+'"' for k in row)+') VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
                from server.catalogue import retire_legacy_bundles, separate_kitchen_library, convert_kitchen_to_feet
                retire_legacy_bundles(conn)
                separate_kitchen_library(conn,body['pricing'])
                convert_kitchen_to_feet(conn,body['pricing'])
                atomic_json(PRICING_PATH,body['pricing'])
                replace_logo(logo)
                conn.commit();store._pricing_cache['raw']=None
            except Exception:
                conn.rollback();atomic_json(PRICING_PATH,before['pricing']);store._pricing_cache['raw']=None
                replace_logo(previous_logo)
                raise
        return {'ok':True}

    @route('POST','/api/drawing')
    def independent_drawing(conn,m,body,q):
        from server.drawing import recognize
        try:return recognize(body)
        except Exception as e:raise api.ApiError('Drawing recognition failed / 图纸识别失败: '+str(e))

    @route('PUT',r'/api/(customers|projects)/(\d+)')
    def independent_contact_edit(conn,m,body,q):
        table=m.group(1);allowed=('name','phone','email','address','note') if table=='customers' else ('name','address','note','customer_id')
        fields={k:body[k] for k in allowed if k in body}
        if fields:
            conn.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',list(fields.values())+[int(m.group(2))]);conn.commit()
        return {'ok':True}

    @route('DELETE',r'/api/(customers|projects)/(\d+)')
    def independent_contact_delete(conn,m,body,q):
        table=m.group(1);ident=int(m.group(2))
        # Quotes carry their own names/addresses, so deleting a directory entry does not erase quotes.
        if table=='customers':
            conn.execute('UPDATE quotes SET customer_id=NULL WHERE customer_id=?',(ident,))
            conn.execute('UPDATE projects SET customer_id=NULL WHERE customer_id=?',(ident,))
        else:conn.execute('UPDATE quotes SET project_id=NULL WHERE project_id=?',(ident,))
        conn.execute('DELETE FROM '+table+' WHERE id=?',(ident,));conn.commit()
        return {'ok':True}

    @route('POST','/api/shutdown')
    def independent_shutdown(conn,m,body,q):
        threading.Timer(.3,lambda:api.SERVER.shutdown()).start()
        return {'ok':True}

    # All standard and custom floors are independently editable in the same configuration.
    original_floors=store.list_floors
    def floors(conn):
        raw=store.pricing_raw()
        return raw.get('floors') if 'floors' in raw else original_floors(conn)
    store.list_floors=floors
    def rooms(cfg): return [dict(r) for r in cfg.rooms()]
    api._rooms_with_extra=rooms
    def rooms(cfg): return [dict(r) for r in cfg.rooms()]
    api._rooms_with_extra=rooms

    # Locked quote exports use the same price and rule snapshot as the displayed locked quote.
    original_export=api._export_quote
    def guarded_export(conn,qid,kind,fmt):
        if kind not in ('customer','internal') or fmt not in ('xlsx','pdf'):raise api.ApiError('Invalid export option / 导出选项错误')
        return original_export(conn,qid,kind,fmt)
    api._export_quote=guarded_export

