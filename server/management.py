"""Management routes for the rebuilt business catalogue and quote price snapshots."""
import copy
import json
import re
from core.business import number
from server import store, catalogue, independent


def install(api):
    def route(method,path):
        def wrap(fn):
            api.ROUTES.insert(0,(method,re.compile('^'+path+'$'),fn.__name__))
            setattr(api,fn.__name__,fn)
            return fn
        return wrap

    @route('GET','/api/catalogue')
    def management_catalogue(conn,m,body,q):
        return catalogue.payload(conn)

    @route('POST','/api/catalogue/materials')
    def management_material(conn,m,body,q):
        return catalogue.save_material(conn,body)

    @route('DELETE',r'/api/catalogue/materials/([A-Za-z0-9_-]+)')
    def management_material_delete(conn,m,body,q):
        return catalogue.delete_material(conn,m.group(1))

    @route('DELETE',r'/api/catalogue/categories/([A-Za-z0-9_]+)')
    def management_category_delete(conn,m,body,q):
        return catalogue.delete_category(conn,m.group(1))

    @route('DELETE',r'/api/catalogue/rates/([A-Za-z0-9_-]+)')
    def management_rate_delete(conn,m,body,q):
        return catalogue.delete_rate(conn,m.group(1))

    @route('POST','/api/catalogue/order')
    def management_order(conn,m,body,q):
        return catalogue.save_order(conn,body.get('key'),body.get('ids'))

    @route('POST','/api/catalogue/rates')
    def management_rate(conn,m,body,q):
        return catalogue.save_rate(conn,body)

    @route('POST','/api/catalogue/category')
    def management_category(conn,m,body,q):
        return catalogue.save_category(conn,body)

    @route('GET',r'/api/quotes/(\d+)/catalogue')
    def management_quote_catalogue(conn,m,body,q):
        quote=store.get_quote(conn,int(m.group(1)))
        if not quote: raise api.ApiError('Quotation not found / 报价不存在',404)
        return api.bootstrap_payload(conn,store.config_for(conn,quote))

    @route('POST',r'/api/quotes/(\d+)/refresh-prices')
    def management_refresh(conn,m,body,q):
        quote=store.get_quote(conn,int(m.group(1)))
        if not quote: raise api.ApiError('Quotation not found / 报价不存在',404)
        if quote['locked']: raise api.ApiError('Revise locked quotation first / 请先创建锁定报价的修订版',409)
        before=store.compute_for(conn,quote)
        updated=dict(copy.deepcopy(quote),pricing_snapshot=copy.deepcopy(store.build_config(conn).raw),mode='retail')
        old_cfg=store.config_for(conn,quote)
        for item in updated['items']:
            item['cat']=old_cfg.category(item['cat']).get('source_key',item['cat'])
        new_cats={c['key']:c for c in updated['pricing_snapshot']['categories']}
        if any(i.get('unit_price') is not None and old_cfg.category(i['cat']).get('pricing_model')!='kitchen_split' and new_cats.get(old_cfg.category(i['cat']).get('source_key',i['cat']),{}).get('pricing_model')=='kitchen_split' for i in quote['items']):
            raise api.ApiError('Clear old kitchen manual bundle rates before updating to foot carcass rates / 请先清空旧橱柜行的含门手动单价，再更新为按英尺柜体计价；更新后可填写新的柜体单价',409)
        converted=[]
        for previous,item in zip(quote['items'],updated['items']):
            new=updated['pricing_snapshot']['prices'].get(item['cat'],{}).get(item['material'],{})
            old=old_cfg.price_entry(previous['cat'],item['material'])
            if item.get('unit_price') is not None and old_cfg.category(previous['cat']).get('pricing_model')=='kitchen_split' and old.get('unit')=='m' and new.get('unit')=='ft':
                item['unit_price']=round(round(item['unit_price'],2)*old_cfg.mm_per_ft/1000,8)
            if item['cat']!=previous['cat'] or item.get('unit_price')!=previous.get('unit_price'):converted.append(item)
        after=store.compute_for(conn,updated)
        if not body.get('apply'):
            return dict(before=before['summary'],after=after['summary'])
        with conn:
            for item in converted:conn.execute('UPDATE quote_items SET cat=?,unit_price=? WHERE quote_id=? AND id=?',(item['cat'],item.get('unit_price'),quote['id'],item['id']))
            conn.execute('UPDATE quotes SET pricing_snapshot_json=?,mode=? WHERE id=?',
                         (json.dumps(updated['pricing_snapshot'],ensure_ascii=False),'retail',quote['id']))
        return dict(quote=store.get_quote(conn,quote['id']),computed=after)

    @route('POST',r'/api/quotes/(\d+)/cost-policy')
    def management_quote_costs(conn,m,body,q):
        quote=store.get_quote(conn,int(m.group(1)))
        if not quote: raise api.ApiError('Quotation not found / 报价不存在',404)
        if quote['locked']: raise api.ApiError('Revise locked quotation first / 请先修订锁定报价',409)
        raw=copy.deepcopy(store.config_for(conn,quote).raw)
        if raw.get('meta',{}).get('business_version')!=5 and not raw.get('kitchen_pricing'): raise api.ApiError('Update quotation to new rules first / 请先更新为新版计价规则')
        from core.business import DEFAULT_COSTS
        raw['project_costs']={k:number(body.get(k,raw.get('project_costs',{}).get(k,v)),k) for k,v in DEFAULT_COSTS.items()}
        validation=copy.deepcopy(raw.get('kitchen_pricing') or raw)
        validation['project_costs']=raw['project_costs']
        independent.validate_config(validation)
        with conn:
            conn.execute('UPDATE quotes SET pricing_snapshot_json=? WHERE id=?',(json.dumps(raw,ensure_ascii=False),quote['id']))
        quote=store.get_quote(conn,quote['id'])
        return dict(quote=quote,computed=store.compute_for(conn,quote))

    @route('POST',r'/api/quotes/(\d+)/unlock')
    def management_revise(conn,m,body,q):
        quote=store.get_quote(conn,int(m.group(1)))
        if not quote: raise api.ApiError('Quotation not found / 报价不存在',404)
        revised=store.duplicate_quote(conn,quote['id']) if quote['locked'] else quote
        return dict(quote=revised,computed=store.compute_for(conn,revised))
