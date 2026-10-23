'use strict';
const $=id=>document.getElementById(id), $$=(s,p=document)=>Array.from(p.querySelectorAll(s));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bi=(en,cn)=>`${esc(en)}${cn?`<i>${esc(cn)}</i>`:''}`;
const clone=x=>JSON.parse(JSON.stringify(x));
const money=x=>'RM '+Number(x||0).toLocaleString('en-MY',{minimumFractionDigits:2,maximumFractionDigits:2});
const val=id=>$(id).value, num=id=>Number(val(id)||0), set=(id,v)=>{$(id).value=v??'';};
const S={boot:null,q:null,computed:{lines:[],summary:{}},cat:'custom_cabinet',edit:-1,selected:new Set(),undo:[],rev:0,saved:0,saving:null,timer:null,computeSeq:0,previewSeq:0,unit:'mm',roomDrafts:[],dragItem:null,orderSaving:false,choiceOrder:null};
const factors={mm:1,cm:10,inch:25.4,ft:304.8};
let drawingPasteHandler=null;
function toast(text,error=false){$('toast').textContent=text;$('toast').className='show';$('toast').style.background=error?'#9d3e40':'';clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').classList.remove('show'),4500);}
async function api(path,method='GET',data){const r=await fetch(path,{method,headers:data?{'Content-Type':'application/json'}:undefined,body:data?JSON.stringify(data):undefined});let j;try{j=await r.json();}catch{throw Error('Invalid server response / 服务返回格式错误');}if(!r.ok)throw Error(j.error||'Operation failed / 操作失败');return j;}
function run(fn){return async(...args)=>{try{return await fn(...args);}catch(e){console.error(e);toast(e.message,true);}};}
function cat(){return S.boot.categories.find(c=>c.key===S.cat)||S.boot.categories[0];}
function option(v,text){return `<option value="${esc(v)}">${esc(text)}</option>`;}
function fillSelect(id,items,keep){const current=keep??val(id);$(id).innerHTML=items.map(x=>option(x[0],x[1])).join('');if(items.some(x=>x[0]===current))set(id,current);}
function refreshBoot(b){S.boot=b;b.ui_order=b.ui_order||S.config?.ui_order||S.order||{};S.order=b.ui_order;fillSelect('mode',Object.keys(b.price_modes).map(k=>[k,`${({low:'Low / 市场低价',mid:'Mid / 市场中价',high:'High / 市场高价'})[k]||b.price_modes_en[k]}`]));syncRoomOptions();$('floorOptions').innerHTML=b.floors.map(f=>option(f.code,`${f.name_en||f.code} / ${f.name||f.code}`)).join('');if(!b.categories.some(c=>c.key===S.cat))S.cat=b.categories[0].key;selectCategory(S.cat,false);}
function roomTemplate(value){const name=String(value||''),rooms=(S.boot?.rooms||[]).slice().sort((a,b)=>b.name.length-a.name.length),exact=rooms.find(r=>r.name===name);if(exact)return{base:exact,number:0};for(const base of rooms){if(!name.startsWith(base.name))continue;const suffix=name.slice(base.name.length).trim().replace(/^#/,'').trim();if(/^\d+$/.test(suffix))return{base,number:Number(suffix)};}const match=name.match(/^(.*?)(?:\s*#?\s*)(\d+)$/);if(match&&match[1].trim())return{base:{name:match[1].trim(),name_en:match[1].trim()},number:Number(match[2])};return{base:{name,name_en:name},number:0};}
function syncRoomOptions(keep=val('room')){if(!S.boot)return;const bases=S.boot.rooms||[],baseNames=new Set(bases.map(r=>r.name)),names=[...new Set([...(S.roomDrafts||[]),...(S.q?.items||[]).map(i=>i.room).filter(Boolean)])].filter(n=>!baseNames.has(n)),rank=new Map(bases.map((r,i)=>[r.name,i]));names.sort((a,b)=>{const x=roomTemplate(a),y=roomTemplate(b);return(rank.get(x.base.name)??999)-(rank.get(y.base.name)??999)||x.number-y.number||a.localeCompare(b);});$('roomOptions').innerHTML=[...bases.map(r=>[r.name,`${r.name_en||r.name} / ${r.name}`]),...names.map(n=>{const {base,number}=roomTemplate(n);return[n,`${base.name_en||base.name}${number?' '+number:''} / ${n}`];})].map(x=>option(x[0],x[1])).join('');if(keep!==undefined)set('room',keep);}
function addRoomInstance(){assertEditable();const {base}=roomTemplate(val('room')),bare=S.q.items.filter(i=>i.room===base.name);if(bare.length){const used=new Set([...S.roomDrafts,...S.q.items.map(i=>i.room)].map(roomTemplate).filter(x=>x.base.name===base.name&&x.number>0).map(x=>x.number));let first=1;while(used.has(first))first++;const name=base.name+first;undoPoint();bare.forEach(i=>i.room=name);if(!S.roomDrafts.includes(name))S.roomDrafts.push(name);changed();}const numbers=[...S.roomDrafts,...S.q.items.map(i=>i.room)].map(roomTemplate).filter(x=>x.base.name===base.name).map(x=>x.number),number=Math.max(...numbers,0)+1,name=base.name+number;if(!S.roomDrafts.includes(name))S.roomDrafts.push(name);syncRoomOptions(name);toast(`${base.name_en||base.name} ${number} / ${name} added / 已新增`);}
function svgCabinet(w=2400,h=2400,d=600){const tall=Math.max(35,Math.min(77,75*h/Math.max(w,h,1))),wide=Math.max(35,Math.min(74,74*w/Math.max(w,h,1))),x=(100-wide)/2,y=90-tall;return `<svg viewBox="0 0 120 110" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M${x},${y} l15,-10 h${wide} v${tall} l-15,10 Z" fill="#eef1f4" stroke="#a5b1c2"/><path d="M${x},${y} h${wide} v${tall} h-${wide} Z" fill="#faf9f5" stroke="#8c9cb1"/><path d="M${x+wide/2},${y} v${tall} M${x+wide},${y} l15,-10" stroke="#a5b1c2"/><path d="M${x+wide/2-4},${y+tall*.48} v12 M${x+wide/2+4},${y+tall*.48} v12" stroke="#c5aa82" stroke-width="2"/><text x="60" y="105" fill="#748094" font-size="8" text-anchor="middle">${Math.round(w)} × ${Math.round(h)} × ${Math.round(d)}</text></svg>`;}
function renderCategoryPicker(c){
 const choices=S.boot.categories.map(x=>[x.key,`${x.name_en} / ${x.pricing_model==='kitchen_split'?'橱柜—'+x.name.replace(/^橱柜[—－-]?/,''):x.name}`]);
 fillSelect('categorySelect',choices,c.key);
 $('categorySelect').onchange=()=>selectCategory(val('categorySelect'));
}
function updateCarcassPriceCaption(){
 const c=cat(),unit=c.materials.find(m=>m.key===val('material'))?.unit||c.body_unit||'m';
 const label=$('unit_price').parentElement.querySelector('span');
 if(label)label.innerHTML=bi(c.pricing_model==='kitchen_split'?`Carcass price (RM/${unit==='ft'?'FT':unit})`:'Unit price (RM)',c.pricing_model==='kitchen_split'?'仅改柜体单价，柜门另计':'单价，留空自动');
}
function paintChoices(defaults=false){const c=cat();renderCategoryPicker(c);fillSelect('material',c.materials.map(m=>[m.key,`${m.label_en} / ${m.label}`]));fillSelect('door',[['','No door / 无门'],...c.doors.map(m=>[m.key,`${m.label_en} / ${m.label}`])]);$('door').disabled=!c.doors.length;if(defaults&&c.doors.length)set('door',c.doors[0].key);
for(const id of ['material','door']){let hint=$(id+'Caption');if(!hint){hint=document.createElement('small');hint.id=id+'Caption';hint.className='choice-caption';$(id).after(hint);}const update=()=>hint.textContent=$(id).selectedOptions[0]?.textContent||'';$(id).onchange=()=>{update();updateCarcassPriceCaption();preview();};update();}const minimum=c.pricing_model==='kitchen_split'?c.door_min_height_ft:c.min_height_ft;$('minLabel').innerHTML=bi(`Minimum bill ${minimum||0} ft`,c.pricing_model==='kitchen_split'?'柜门最低计价高':'最低计价高');$('minHeight').disabled=!minimum;updateCarcassPriceCaption();renderExtras();}
function selectCategory(key,defaults=true){S.cat=key;const c=cat();paintChoices(defaults);if(defaults){set('height',+(Number(c.default_height_mm||0)/factors[val('unit')]).toFixed(4));set('depth',+(Number(c.std_depth_mm||0)/factors[val('unit')]).toFixed(4));set('unit_price','');}preview();}

// ---- Choice ordering: one persisted catalogue order shared with Management ----
const ORDER_CHANNEL='vouguer-catalogue-order';
function bodyPart(){return cat().pricing_model==='kitchen_split'?'kitchen_body':'body';}
function mergeVisibleOrder(canonical,visible){
 const base=Array.isArray(canonical)?canonical.slice():[],next=base.slice(),slots=[],seen=new Set(),unique=[];
 for(const id of visible||[]){
  if(!id)throw Error('Choice list changed; reopen ordering / 选项已变化，请重新打开排序');
  if(seen.has(id))throw Error('Duplicate choice in list; reopen ordering / 选项重复，请重新打开排序');
  seen.add(id);unique.push(id);
 }
 base.forEach((id,index)=>{if(unique.includes(id))slots.push(index);});
 if(!unique.length||slots.length!==unique.length)throw Error('Choice list changed; reopen ordering / 选项已变化，请重新打开排序');
 slots.forEach((slot,index)=>next[slot]=unique[index]);
 return next;
}
function orderBaseline(saved,canonical){
 const base=[];for(const id of canonical||[])if(id&&!base.includes(id))base.push(id);
 const kept=[];for(const id of saved||[])if(base.includes(id)&&!kept.includes(id))kept.push(id);
 return [...kept,...base.filter(id=>!kept.includes(id))];
}
function rateIndex(data,category){const map={};for(const rate of data.rates||[])if(rate.category_key===category&&rate.enabled)map[rate.mat_key]=rate;return map;}
function choiceWrites(scope,visibleIds,data){
 const category=cat().key;
 if(scope==='categories')return [{key:'categories',ids:mergeVisibleOrder(orderBaseline(data.orders?.categories,(data.categories||[]).map(c=>c.key)),visibleIds)}];
 if(scope==='extras')return [{key:'extras',ids:mergeVisibleOrder(orderBaseline(data.orders?.extras,(data.config?.extras?.items||[]).map(e=>e.key)),visibleIds)}];
 // ONE write per Quick entry move: the operated part's library order. Persisting a
 // category rate list here would carry a stale snapshot of the *other* part and could
 // overwrite a newer sort made in the Management window. Bootstrap and Management both
 // derive the per-part effective order from this library stamp (library_wins), so the
 // move is still visible everywhere, immediately and after refresh.
 const part=scope==='carcass'?bodyPart():'door',rates=rateIndex(data,category);
 const materials=visibleIds.map(key=>rates[key]?.material_id).filter(Boolean);
 if(!materials.length)throw Error('These choices are not linked to saved materials / 所选选项未关联材料');
 return [{key:'materials:'+part,ids:mergeVisibleOrder(orderBaseline(data.orders?.['materials:'+part],(data.materials||[]).filter(m=>m.part===part).map(m=>m.id)),materials)}];
}
async function choiceOrderData(){
 const [catalog,raw]=await Promise.all([api('/api/catalogue'),api('/api/config')]);
 return {...catalog,config:raw.config};
}
function orderBus(){
 if(S.orderBus!==undefined)return S.orderBus;
 try{S.orderBus=typeof BroadcastChannel==='undefined'?null:new BroadcastChannel(ORDER_CHANNEL);}catch(e){S.orderBus=null;}
 if(S.orderBus)S.orderBus.onmessage=()=>run(refreshChoices)();
 return S.orderBus;
}
function announceOrder(key){const bus=orderBus();if(bus)try{bus.postMessage({key});}catch(e){console.error(e);}}
function orderChoiceList(title,items,scope){
 return `<section class="order-section"><h3>${title}</h3><div class="order-list">${items.map((item,index)=>`<div class="order-line"><span>${esc(item.text)}</span><button type="button" data-choice-scope="${scope}" data-choice-index="${index}" data-choice-delta="-1" aria-label="Move up / 上移" title="Move up / 上移" ${index===0?'disabled':''}>↑</button><button type="button" data-choice-scope="${scope}" data-choice-index="${index}" data-choice-delta="1" aria-label="Move down / 下移" title="Move down / 下移" ${index===items.length-1?'disabled':''}>↓</button></div>`).join('')||`<p class="hint">${bi('No choices in this list','此列表暂无可排序选项')}</p>`}</div></section>`;
}
function choiceIds(scope){
 if(scope==='categories')return S.boot.categories.map(c=>c.key);
 if(scope==='extras')return cat().extras.map(e=>e.key);
 if(scope==='carcass')return cat().materials.map(m=>m.key);
 return cat().doors.map(m=>m.key);
}
function drawChoiceOrder(){
 const list=$('orderLists');if(!list)return;const c=cat(),busy=Boolean(S.orderSaving);
 list.innerHTML=orderChoiceList(bi('Categories','品类'),S.boot.categories.map(x=>({text:`${x.name_en} / ${x.name}`})),'categories')
  +orderChoiceList(bi('Carcass materials in this category','本品类柜体材料'),c.materials.map(x=>({text:`${x.label_en} / ${x.label}`})),'carcass')
  +orderChoiceList(bi('Door finishes in this category','本品类柜门材料'),c.doors.map(x=>({text:`${x.label_en} / ${x.label}`})),'doors')
  +orderChoiceList(bi('Add-ons in this category','本品类增项'),c.extras.map(x=>({text:`${x.name_en} / ${x.name}`})),'extras');
 $$('[data-choice-scope]',list).forEach(b=>{
  if(busy)b.disabled=true;
  b.onclick=run(()=>moveChoice(b.dataset.choiceScope,Number(b.dataset.choiceIndex),Number(b.dataset.choiceDelta)));
 });
}
async function moveChoice(scope,index,delta){
 if(S.orderSaving)return;                       // 保存中：忽略后续点击，避免基于旧列表的并发保存
 const ids=choiceIds(scope),target=index+delta;
 if(target<0||target>=ids.length)return;
 const next=ids.slice();[next[index],next[target]]=[next[target],next[index]];
 await persistChoiceOrder(scope,next,scope,target);
}
async function persistChoiceOrder(scope,visibleIds,focusScope,focusIndex){
 if(S.orderSaving)return;
 S.orderSaving=true;
 if($('orderLists'))drawChoiceOrder();
 try{
  const data=S.choiceOrder||await choiceOrderData();
  const writes=choiceWrites(scope,visibleIds,data);
  for(const write of writes)await api('/api/catalogue/order','POST',write);
  announceOrder(writes.map(write=>write.key).join(','));
  await refreshChoices();
  toast('Choice order saved / 选项顺序已保存');
 }finally{
  S.orderSaving=false;
  if($('orderLists'))drawChoiceOrder();
 }
 if(focusScope!=null)$$('[data-choice-scope]').find(b=>b.dataset.choiceScope===focusScope&&Number(b.dataset.choiceIndex)===focusIndex)?.focus();
}
async function openChoiceOrder(){
 if(S.orderSaving)return;
 if(!S.boot)throw Error('Quotation catalogue is still loading / 选项仍在加载');
 S.choiceOrder=await choiceOrderData();
 modal(bi('Choice order','选项排序'),`<p class="notice">${bi('Order applies to Quick entry and Management at once, in other windows and after restart. Prices, materials and quotation lines are not changed.','排序会立即同步到快速录入与后台管理，其他窗口及重启后一致；不会改动价格、材料和报价明细。')}</p><div id="orderLists"></div>`);
 drawChoiceOrder();
}
function draftFields(){
 const out={material:val('material'),door:val('door'),extras:[],sizes:[]},root=$('extras');
 $$('[data-extra]',root).forEach(i=>out.extras.push([i.dataset.extra,i.value]));
 $$('[data-ew], [data-eh], [data-el]',root).forEach(i=>out.sizes.push([i.dataset.ew?'w':i.dataset.eh?'h':'l',i.dataset.ew||i.dataset.eh||i.dataset.el,i.value]));
 return out;
}
function applyDraftFields(draft){
 const root=$('extras');
 $$('[data-extra]',root).forEach(i=>{const hit=draft.extras.find(x=>x[0]===i.dataset.extra);if(hit)i.value=hit[1];});
 $$('[data-ew], [data-eh], [data-el]',root).forEach(i=>{const kind=i.dataset.ew?'w':i.dataset.eh?'h':'l',key=i.dataset.ew||i.dataset.eh||i.dataset.el,hit=draft.sizes.find(x=>x[0]===kind&&x[1]===key);if(hit)i.value=hit[2];});
 if(draft.material&&$$('option',$('material')).some(o=>o.value===draft.material))set('material',draft.material);
 if(draft.door!==undefined&&$$('option',$('door')).some(o=>o.value===draft.door))set('door',draft.door);
}
async function refreshChoices(){
 if(!S.boot)return;
 const payload=await api('/api/bootstrap');
 if(!S.boot||!payload?.categories)return;
 const draft=draftFields(),keep=S.cat;
 S.choiceOrder=null;
 S.boot.categories=payload.categories;S.boot.rooms=payload.rooms;S.boot.floors=payload.floors;S.boot.extras_all=payload.extras_all;
 if(!S.boot.categories.some(c=>c.key===keep))S.cat=S.boot.categories[0]?.key||keep;
 paintChoices(false);applyDraftFields(draft);
 $('material').onchange?.();$('door').onchange?.();
 if($('orderLists'))drawChoiceOrder();
 preview();
}
function watchCatalogueOrder(){
 orderBus();
 let last=0;
 const refresh=()=>{const now=Date.now();if(now-last<1200)return;last=now;if(S.boot)run(refreshChoices)();};
 window.addEventListener('focus',refresh);
 document.addEventListener?.('visibilitychange',()=>{if(!document.hidden)refresh();});
}
function renderExtras(){
 const extras=cat().extras;
 $('extras').innerHTML=extras.map(e=>e.auto_with_cabinet?`<div class="extra"><label>${bi(e.name_en,e.name)}<small>${money(e.price)} / m</small></label><output data-auto-price="${esc(e.key)}">Auto: cabinet length × quantity / 自动按柜体总长度计入</output></div>`:`<div class="extra${e.basis==='area'?' area-extra':''}">
 <label>${bi(e.name_en,e.name)}<small>${money(e.price)} / ${esc(e.unit)} · ${bi(e.basis==='area'?'Area':e.basis==='length'?'Length':'Quantity',e.basis==='area'?'面积':e.basis==='length'?'长度':'数量')}</small></label>
 <label class="extra-qty">${bi(e.basis==='qty'?`Total usage (${e.unit})`:'Pieces',e.basis==='qty'?`本行总用量（${e.unit}，0为不选）`:'件数')}<input data-extra="${esc(e.key)}" type="number" min="0" step="any" value="0" aria-label="${esc(e.name_en+' / '+e.name)} quantity"></label>
 ${e.basis==='area'?`<div class="glass-dims"><label>${bi('Width (mm)','宽')}<input data-ew="${esc(e.key)}" type="number" min="0" step="any" placeholder="Auto / 随柜体" aria-label="${esc(e.name_en+' width (mm) / '+e.name+'宽（毫米）')}"></label><span>×</span><label>${bi('Height (mm)','高')}<input data-eh="${esc(e.key)}" type="number" min="0" step="any" placeholder="Auto / 随柜体" aria-label="${esc(e.name_en+' height (mm) / '+e.name+'高（毫米）')}"></label></div>
 <output class="area-price" data-area-price="${esc(e.key)}" aria-live="polite">Not included / 未计入（数量0）</output>
 <p class="area-hint">${e.charge_kind==='upgrade'?'Upgrade difference only; standard door price remains.<i>玻璃门按升级差价另加，普通柜门价保留</i>':''}Sizing adds 1; quantity 0 excludes. Blank follows actual cabinet size.<i>填尺寸自动计1件；数量0取消；留空按柜体实际尺寸</i></p>`:''}
 ${e.basis==='length'?`<label class="quartz-length">${bi('Independent length (mm)','独立长度（毫米）')}<input data-el="${esc(e.key)}" type="number" min="0" step="any" placeholder="Auto / 随柜体长度" aria-label="${esc(e.name_en+' length (mm) / '+e.name+'长度（毫米）')}"></label>
 <output class="area-price" data-length-price="${esc(e.key)}" aria-live="polite">Not included / 未计入（数量0）</output>
 <p class="area-hint">Optional mm length; blank follows cabinet length. Rate unit shown above.<i>可填独立毫米长度；留空跟随柜体长度；按上方所示单价单位计算。填长度自动计1件，数量0取消。</i></p>`:''}</div>`).join('');
 $$('input',$('extras')).forEach(i=>i.addEventListener('input',()=>{
  const key=i.dataset.ew||i.dataset.eh||i.dataset.el;
  if(key&&Number(i.value)>0){const q=$$('[data-extra]',$('extras')).find(x=>x.dataset.extra===key);if(q&&Number(q.value)<=0)q.value=1;}
  preview();
 }));
}
function updateExtraPrices(it,line){
 $$('[data-auto-price]').forEach(o=>{const e=line?.extras_list?.find(x=>x.key===o.dataset.autoPrice);o.textContent=e?`${e.measure.toFixed(4)} m × ${money(e.price)} = ${money(e.amount)} · Auto / 自动计入`:'Auto: cabinet total length / 自动按柜体总长度计入';});
 $$('[data-area-price]').forEach(o=>{
  const key=o.dataset.areaPrice,q=Number(it.extras[key]||0),sz=it.extras_size[key]||{},w=sz.w_mm??it.length_mm,h=sz.h_mm??it.height_mm;
  if(!(q>0)){o.textContent='Not included / 未计入（数量0）';return;}
  if(!(w>0&&h>0)){o.textContent='Enter positive dimensions and whole quantity / 请填写有效宽高和整数数量';return;}
  const e=line?.extras_list?.find(x=>x.key===key);
  if(!e){o.textContent='Calculating… / 计算中';return;}
  const dim=n=>Number(n).toLocaleString('en-MY',{maximumFractionDigits:4});
  o.innerHTML=`<span>${dim(w)} × ${dim(h)} mm${q!==1?` × ${q} pcs / 件`:''}</span><strong>${Number(e.measure).toLocaleString('en-MY',{minimumFractionDigits:4,maximumFractionDigits:4})} ${esc(e.unit||'ft²')} × ${money(e.price)} = ${money(e.amount)}</strong>`;
 });
 $$('[data-length-price]').forEach(o=>{
  const key=o.dataset.lengthPrice,q=Number(it.extras[key]||0),custom=it.extras_size[key]?.l_mm,length=custom??it.length_mm;
  if(!(q>0)){o.textContent='Not included / 未计入（数量0）';return;}
  if(!Number.isFinite(length)||!(length>0)){o.textContent='Enter positive length or clear for automatic sizing / 请填有效长度，或清空以自动跟随';return;}
  const e=line?.extras_list?.find(x=>x.key===key);
  if(!e){o.textContent='Calculating… / 计算中';return;}
  o.innerHTML=`<span>${length.toLocaleString('en-MY',{maximumFractionDigits:4})} mm${q!==1?` × ${q} pcs / 件`:''} · ${custom==null?'Auto / 随柜体':'Custom / 独立长度'}</span><strong>${Number(e.measure).toLocaleString('en-MY',{minimumFractionDigits:4,maximumFractionDigits:4})} ${esc(e.unit||'ft')} × ${money(e.price)} = ${money(e.amount)}</strong>`;
 });
}
function validateExtras(it){
 for(const e of cat().extras){
  const q=Number(it.extras[e.key]||0);
  if(q>0&&e.charge_kind==='upgrade'&&(!it.door||it.door==='none'))throw Error('Choose a standard door first / 玻璃升级差价须先选择基础柜门');
  if(q>0&&['pcs','set','个','套'].includes(e.unit)&&!Number.isInteger(q))throw Error('Add-on quantity must be a whole number / 增项数量须为整数');
  if(e.key==='quartz'&&e.basis==='length'&&q>0){
   const length=it.extras_size[e.key]?.l_mm;
   if(length!=null&&(!Number.isFinite(length)||length<=0))throw Error('Enter positive quartz length in mm, or leave blank / 请填写大于零的石英石毫米长度，或清空自动跟随');
  }
  if(e.basis!=='area'||!q)continue;
  const sz=it.extras_size[e.key]||{};
  if(!((sz.w_mm??it.length_mm)>0&&(sz.h_mm??it.height_mm)>0))throw Error('Enter positive glass width and height / 请填写大于零的玻璃宽高');
 }
}
function buildItem(){const f=factors[val('unit')], extras={},sizes={};$$('[data-extra]').forEach(i=>{if(+i.value>0)extras[i.dataset.extra]=+i.value;});$$('[data-ew]').forEach(i=>{const key=i.dataset.ew,h=$$('[data-eh]').find(x=>x.dataset.eh===key);if(+i.value||+h.value)sizes[key]={w_mm:+i.value||num('length')*f,h_mm:+h.value||num('height')*f};});$$('[data-el]').forEach(i=>{if(i.value!=='')sizes[i.dataset.el]={l_mm:Number(i.value)};});return {floor:val('floor').trim()||'GF',room:val('room'),cat:S.cat,material:val('material'),door:val('door'),cab_name:val('cab_name'),cab_name_en:(S.edit>=0&&val('cab_name')===S.editCabName?S.editCabNameEn:''),length_mm:num('length')*f,height_mm:num('height')*f,depth_mm:num('depth')*f,qty:num('qty'),unit:val('unit'),unit_price:val('unit_price')===''?null:num('unit_price'),nonstd:val('nonstd')==='auto'?null:val('nonstd')==='yes',apply_min_height:$('minHeight').checked,note:val('note'),note_en:val('note_en'),room_note:val('room_note'),room_note_en:val('room_note_en'),extras,extras_size:sizes,led_type:$('led').checked?'yes':'none',led_qty:num('led_qty'),led_unit:'m',led_power:$('led_power').checked,led_sensor:$('led_sensor').checked};}
function validate(it){validateExtras(it);if(!it.material)throw Error('Select an available material / 请选择已启用材料');if(!(it.length_mm>0))throw Error('Length must be greater than zero / 长度须大于零');if(it.height_mm<0||it.depth_mm<0)throw Error('Dimensions must not be negative / 尺寸不可为负');if(cat().measure==='area'&&!(it.height_mm>0))throw Error('Enter the actual height / 请填写实际高度');if(!Number.isInteger(it.qty)||it.qty<1)throw Error('Quantity must be a positive integer / 数量须为正整数');}
function headers(){return {customer:val('customer'),project:val('project'),quote_no:val('quote_no'),quote_date:val('quote_date'),mode:val('mode'),discount:num('discount'),deposit_rate:num('depositPercent')/100};}
function normalizeFloors(){S.q.items.forEach(it=>{const f=(it.floor||'GF').trim(),up=f.toUpperCase().replace(/ /g,'');it.floor=S.boot.floor_codes.includes(up)?up:({G:'GF',GROUND:'GF',GROUNDFLOOR:'GF',ROOF:'RF',B1F:'B1',B2F:'B2'})[up]||f;});}
function undoPoint(){S.undo.push(clone(S.q.items));if(S.undo.length>30)S.undo.shift();}
function assertEditable(){if(S.q.locked)throw Error('Unlock prices before editing / 请先解锁再修改');}
function changed(){assertEditable();Object.assign(S.q,headers());S.rev++;$('saveState').textContent='Saving… / 正在保存';clearTimeout(S.timer);S.timer=setTimeout(run(save),550);recompute();}
async function save(){clearTimeout(S.timer);if(S.q.locked)return;if(S.saving){await S.saving;if(S.saved>=S.rev)return;}S.saving=(async()=>{while(S.saved<S.rev){const rev=S.rev,qid=S.q.id;const payload={header:{...S.q,...headers()},items:clone(S.q.items)};const result=await api('/api/quotes/'+qid,'PUT',payload);if(S.q.id!==qid)return;S.saved=rev;S.q.updated_at=result.quote.updated_at;$('saveState').textContent=S.saved===S.rev?'Saved locally / 已保存到本机':'Saving… / 正在保存';}})();try{await S.saving;}catch(e){$('saveState').textContent='Save failed / 保存失败';throw e;}finally{S.saving=null;}}
async function recompute(){if(!S.q||S.q.locked){render();return;}const seq=++S.computeSeq;normalizeFloors();try{const r=await api('/api/compute','POST',{items:S.q.items,header:{...S.q,...headers()}});if(seq!==S.computeSeq)return;S.computed=r;render();}catch(e){if(seq===S.computeSeq)toast(e.message,true);}}
function adopt(result){S.computeSeq++;S.q=result.quote;setTimeout(run(loadQuoteCatalogue),0);S.q.items=S.q.items||[];S.roomDrafts=[];S.computed=result.computed;S.rev=0;S.saved=0;S.undo=[];S.selected.clear();S.edit=-1;for(const id of ['customer','project','quote_no','quote_date','mode','discount'])set(id,S.q[id]);set('depositPercent',+(100*S.q.deposit_rate).toFixed(2));localStorage.setItem('vouguer-next-v4-quote',S.q.id);$('saveState').textContent='Saved locally / 已保存到本机';resetEntry();render();}
async function newQuote(){await save();const result=await api('/api/quotes','POST',{quote_date:localDate()});S.cat=S.boot.categories.some(c=>c.key==='custom_cabinet')?'custom_cabinet':S.boot.categories[0].key;S.unit='mm';set('unit','mm');set('floor',S.boot.floors[0]?.code||'GF');set('room',S.boot.rooms[0]?.name||'');adopt(result);loadQuoteCatalogue();toast('New quotation created / 已新建报价');}
function localDate(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
function resetEntry(){S.edit=-1;['cab_name','length','unit_price','note','note_en','room_note','room_note_en'].forEach(id=>set(id,''));set('qty',1);set('nonstd','auto');$('minHeight').checked=true;for(const id of ['led','led_power','led_sensor'])$(id).checked=false;set('led_qty',0);selectCategory(S.cat,true);$('entryTitle').innerHTML=bi('Quick entry','快速录入');$('addBtn').innerHTML='＋ '+bi('Add to quotation','添加到报价单')+'<kbd>Enter</kbd>';$('cancelEdit').classList.add('hidden');}
function editItem(index){assertEditable();const it=S.q.items[index];S.edit=index;S.editCabName=it.cab_name||'';S.editCabNameEn=it.cab_name_en||'';set('unit','mm');S.unit='mm';selectCategory(it.cat,false);for(const id of ['floor','room','cab_name','material','door','qty','unit_price','note','note_en','room_note','room_note_en'])set(id,it[id]);for(const id of ['material','door'])$(id).onchange();set('length',it.length_mm);set('height',it.height_mm);set('depth',it.depth_mm);set('nonstd',it.nonstd===null||it.nonstd===undefined?'auto':it.nonstd?'yes':'no');$('minHeight').checked=it.apply_min_height!==false;$('led').checked=it.led_type==='yes';set('led_qty',it.led_qty||0);$('led_power').checked=!!it.led_power;$('led_sensor').checked=!!it.led_sensor;$$('[data-extra]').forEach(i=>i.value=(it.extras||{})[i.dataset.extra]||0);$$('[data-ew]').forEach(i=>i.value=it.extras_size?.[i.dataset.ew]?.w_mm||'');$$('[data-eh]').forEach(i=>i.value=it.extras_size?.[i.dataset.eh]?.h_mm||'');$$('[data-el]').forEach(i=>i.value=it.extras_size?.[i.dataset.el]?.l_mm??'');$('entryTitle').innerHTML=bi(`Edit item ${index+1}`,'修改明细');$('addBtn').innerHTML=bi('Save item changes','保存行修改')+'<kbd>Enter</kbd>';$('cancelEdit').classList.remove('hidden');preview();$('length').focus();}
function addItem(){assertEditable();const it=buildItem();validate(it);undoPoint();const editing=S.edit>=0;if(editing)S.q.items[S.edit]=it;else S.q.items.push(it);S.selected.clear();changed();if(editing)resetEntry();$('length').focus();toast('Item saved / 明细已保存');}
function preview(){
 clearTimeout(preview.timer);
 const seq=++S.previewSeq;
 preview.timer=setTimeout(run(async()=>{
  const it=buildItem();
  $('cabinetPreview').innerHTML=svgCabinet(it.length_mm||2400,it.height_mm||2400,it.depth_mm);
  $('addonsCount').textContent=Object.keys(it.extras).length+(it.led_type==='yes'?1:0);
  updateExtraPrices(it);
  if(!it.length_mm&&!Object.keys(it.extras).length&&it.led_type!=='yes'){
   $('lineAmount').textContent=money(0);$('lineBasis').textContent='Enter dimensions / 输入尺寸开始计算';return;
  }
  try{validateExtras(it);}catch(e){$('lineAmount').textContent='—';$('lineBasis').textContent=e.message;return;}
  const r=await api('/api/compute','POST',{items:[it],header:{...S.q,mode:val('mode')}});
  if(seq!==S.previewSeq)return;
  const l=r.lines[0];
  $('lineAmount').textContent=money(l.amount);
  const addons=Number(l.extras_amount||0)+Number(l.led_amount||0);
  $('lineBasis').textContent=l.pricing_model==='kitchen_split'?l.basis:`${l.measure} ${l.unit_en||l.unit} × ${l.factor} × ${money(l.unit_price)} × ${it.qty}${addons?' + Add-ons / 增项 '+money(addons):''}`;
  updateExtraPrices(it,l);
 }),160);
}
function render(){if(!S.q||S.dragItem)return;renderProjectCosts();syncRoomOptions();$('documentNo').textContent=S.q.quote_no||'New quotation / 新报价';$('lockBtn').innerHTML=S.q.locked?bi('Create revision','创建修订版'):bi('Lock prices','锁价');$('addBtn').disabled=S.q.locked;$('addRoomBtn').disabled=S.q.locked;for(const id of ['customer','project','quote_no','quote_date','mode','discount','depositPercent'])$(id).disabled=S.q.locked;const summary=S.computed.summary||{};for(const [id,key] of [['subtotal','total'],['deposit','deposit'],['grandTotal','net_total']])$(id).textContent=money(summary[key]);$('listCount').textContent=`${S.q.items.length} items / ${S.q.items.length} 项${S.q.locked?' · Locked snapshot / 已锁价快照':''}`;$('selectedCount').textContent=S.selected.size?`${S.selected.size} selected / 已选`:'';const filter=val('search').toLowerCase(),canReorder=!S.q.locked&&!filter;const pairs=S.q.items.map((it,i)=>({it,i,l:S.computed.lines[i]||{}})).filter(p=>JSON.stringify(p.it).toLowerCase().includes(filter));if(!S.q.items.length){$('quoteList').innerHTML=`<div class="empty">${svgCabinet()}<h3>Your next space starts here.<i>从一组尺寸，开始一份报价</i></h3><p>Add a cabinet on the left, or explore the sample quotation.<br>在左侧录入柜体，或载入示例体验完整报价。</p><button id="emptyDemo">${bi('Explore sample quotation','载入示例报价')}</button></div>`;$('emptyDemo').onclick=run(loadDemo);return;}let html=`<table><thead><tr><th>${bi('Order','排序')}</th><th>${bi('Product / room','柜体／区域')}</th><th>${bi('Dimensions (mm)','长 × 高 × 深')}</th><th>${bi('Material','材料')}</th><th>${bi('Qty','数量')}</th><th class="money">${bi('Amount (RM)','本行金额')}</th><th></th></tr></thead><tbody>`,floor=null;for(const [position,p] of pairs.entries()){const {it,i,l}=p;if(floor!==it.floor){floor=it.floor;const f=S.boot.floors.find(f=>f.code===floor),end=pairs.findIndex((p,j)=>j>position&&p.it.floor!==floor),total=pairs.slice(position,end<0?pairs.length:end).reduce((a,p)=>a+(p.l.amount||0),0);html+=`<tr class="floor-row"><td colspan="7"><strong>${esc(floor)} / ${esc(f?.name_en||floor)}</strong><span class="floor-sum">${money(total)}</span></td></tr>`;}html+=`<tr class="item ${S.selected.has(i)?'selected':''}" data-index="${i}"><td class="item-order"><button type="button" class="drag-handle" data-drag="${i}" draggable="false" ${canReorder?'':'disabled'} title="${filter?'Clear filter to reorder / 清空筛选后排序':'Drag up or down; arrow keys also work / 按住上下拖动，也可用方向键'}" aria-label="Drag item ${i+1} to reorder / 拖动第${i+1}项排序">⠿</button><span class="item-number">${i+1}</span><input data-check="${i}" type="checkbox" ${S.selected.has(i)?'checked':''} aria-label="Select item ${i+1} / 选择第${i+1}项"></td><td><strong>${esc(it.cab_name||l.cat_name||it.cat)}</strong>${l.pricing_model==='kitchen_split'?`<small>${bi('Kitchen cabinets · '+(l.cat_name_en||''),'橱柜—'+String(l.cat_name||'').replace(/^橱柜[—－-]?/,''))}</small>`:''}<small>${esc(l.room_en&&l.room_en!==it.room?`${l.room_en} / ${it.room}`:it.room)}</small></td><td class="dims-cell">${[it.length_mm,it.height_mm,it.depth_mm].map(n=>Number(n||0).toLocaleString('en',{maximumFractionDigits:1})).join(' × ')}<small>${l.measure||0} ${esc(l.unit_en||l.unit||'')} · × ${l.factor||1}</small></td><td>${esc(l.material_label_en||it.material)}<i>${esc(l.material_label||'')}</i>${l.price_override?`<span class="badge">Manual price / 手动单价</span>`:''}${l.extras_amount||l.led_amount?`<span class="badge">Add-ons / 含增项</span>`:''}</td><td>${it.qty}</td><td class="money"><strong>${money(l.amount)}</strong><small>${money(l.unit_price)} / ${esc(l.unit_en||l.unit||'')}${l.pricing_model==='kitchen_split'?` carcass / 柜体<br>Door / 柜门 ${money(l.door_amount)}`:''}</small></td><td class="row-actions"><button data-edit="${i}" title="Edit / 修改">✎</button><button data-copy="${i}" title="Duplicate / 复制">⧉</button></td></tr>`;}html+='</tbody></table>';if(!pairs.length)html+='<div class="empty">No matching items / 没有匹配的明细</div>';$('quoteList').innerHTML=html;$$('[data-index]').forEach(r=>r.ondblclick=run(()=>editItem(+r.dataset.index)));$$('[data-edit]').forEach(b=>b.onclick=run(()=>editItem(+b.dataset.edit)));$$('[data-copy]').forEach(b=>b.onclick=run(()=>duplicate([+b.dataset.copy])));$$('[data-check]').forEach(c=>c.onchange=()=>{c.checked?S.selected.add(+c.dataset.check):S.selected.delete(+c.dataset.check);render();});bindItemDrag();}
function duplicate(indices){assertEditable();if(!indices.length)return;undoPoint();S.q.items.push(...indices.map(i=>clone(S.q.items[i])));S.selected.clear();changed();}
function moveItem(from,to){
 assertEditable();
 if(val('search'))throw Error('Clear the filter before reordering / 请先清空筛选再调整顺序');
 if(from===to||from<0||to<0||from>=S.q.items.length||to>=S.q.items.length)return;
 const order=S.q.items.map((_,i)=>i);order.splice(to,0,order.splice(from,1)[0]);
 undoPoint();
 S.q.items=order.map(i=>S.q.items[i]);
 S.computed.lines=order.map((i,n)=>({...S.computed.lines[i],idx:n+1}));
 S.selected=new Set([...S.selected].map(i=>order.indexOf(i)));
 if(S.edit>=0){S.edit=order.indexOf(S.edit);$('entryTitle').innerHTML=bi(`Edit item ${S.edit+1}`,'修改明细');}
 changed();render();toast('Item order saved automatically / 明细顺序将自动保存');
}
function bindItemDrag(){
 const list=$('quoteList');
 const clearMarks=()=>$$('.drop-before,.drop-after',list).forEach(r=>r.classList.remove('drop-before','drop-after'));
 $$('[data-drag]').forEach(handle=>{
  let start=null,target=null,timer=null;
  const updateTarget=()=>{
   if(!start?.moved)return;
   const box=list.getBoundingClientRect(),y=start.y;
   if(y<box.top+28)list.scrollTop-=16;
   else if(y>box.bottom-28)list.scrollTop+=16;
   clearMarks();target=null;
   const row=document.elementFromPoint(start.x,y)?.closest('[data-index]');
   if(!row||!list.contains(row))return;
   const rect=row.getBoundingClientRect(),after=y>rect.top+rect.height/2;
   target=+row.dataset.index+(after?1:0);
   row.classList.add(after?'drop-after':'drop-before');
  };
  const finish=drop=>{
   if(!start)return;
   const from=S.q.items.indexOf(S.dragItem),moved=start.moved,id=start.id;
   let to=target;if(from<to)to--;
   start=null;S.dragItem=null;clearInterval(timer);clearMarks();
   if(handle.hasPointerCapture(id))handle.releasePointerCapture(id);
   if(drop&&moved&&to!==null)moveItem(from,to);
   render();
  };
  handle.onpointerdown=e=>{
   if(e.button!==0||S.q.locked||val('search'))return;
   e.preventDefault();handle.focus();
   S.dragItem=S.q.items[+handle.dataset.drag];
   start={id:e.pointerId,x:e.clientX,y:e.clientY,originX:e.clientX,originY:e.clientY,moved:false};target=null;
   handle.setPointerCapture(e.pointerId);
  };
  handle.onpointermove=e=>{
   if(!start)return;start.x=e.clientX;start.y=e.clientY;
   if(!start.moved){
    if(Math.hypot(start.x-start.originX,start.y-start.originY)<4)return;
    start.moved=true;handle.closest('[data-index]').classList.add('dragging');
    timer=setInterval(updateTarget,50);
   }
   updateTarget();
  };
  handle.onpointerup=run(()=>finish(true));
  handle.onpointercancel=()=>finish(false);
  handle.onlostpointercapture=()=>finish(false);
  handle.onkeydown=run(e=>{
   if(e.key!=='ArrowUp'&&e.key!=='ArrowDown')return;e.preventDefault();
   const i=+handle.dataset.drag,to=i+(e.key==='ArrowUp'?-1:1);moveItem(i,to);
   $$('[data-drag]').find(b=>+b.dataset.drag===to)?.focus();
  });
 });
}
function modal(title,body,buttons=[],sub=''){const m=$('modal');$('modalTitle').innerHTML=title;$('modalSubtitle').textContent=sub;$('modalBody').innerHTML=body;$('modalFooter').innerHTML='';buttons.forEach(({text,action,primary=false})=>{const b=document.createElement('button');b.innerHTML=text;b.className=primary?'primary':'';b.onclick=run(action);$('modalFooter').appendChild(b);});if(!m.open)m.showModal();}
function closeModal(){if(S.manageDirty&&!confirm('Discard unsaved management changes? / 放弃未保存的管理修改？'))return;S.manageDirty=false;$('modal').close();}
async function loadDemo(){assertEditable();if(S.q.items.length&&!confirm('Replace current items with sample data? / 用示例替换当前明细？'))return;const demo=await fetch('/demo.json').then(r=>r.json());undoPoint();S.q.items=demo;S.selected.clear();changed();toast('Sample loaded; prices use your current price list / 已载入示例，按当前价格计算');}
async function history(){await save();const list=await api('/api/quotes');const rows=list.quotes||list;modal(bi('Saved quotations','历史报价'),`<input id="historySearch" placeholder="Search customer or project / 筛选客户、项目"><div id="historyRows"></div>`);const draw=()=>{$('historyRows').innerHTML=rows.filter(q=>JSON.stringify([q.quote_no,q.customer,q.project]).toLowerCase().includes(val('historySearch').toLowerCase())).map(q=>`<div class="history-row"><div><strong>${esc(q.quote_no)} ${q.locked?'🔒':''}</strong><p>${esc(q.customer||'No customer / 未填写客户')} · ${esc(q.project||'No project / 未填写项目')}</p><small>${esc(q.quote_date)} · ${q.item_count} items / 项</small></div><div class="history-actions"><strong>${money(q.total)}</strong><button data-openq="${q.id}">${bi('Open','打开')}</button><button data-copyq="${q.id}">${bi('Copy','复制')}</button><button class="danger" data-deleteq="${q.id}">${bi('Delete','删除')}</button></div></div>`).join('')||'<p>No saved quotations / 暂无历史报价</p>';$$('[data-openq]').forEach(b=>b.onclick=run(async()=>{adopt(await api('/api/quotes/'+b.dataset.openq));$('modal').close();}));$$('[data-copyq]').forEach(b=>b.onclick=run(async()=>{adopt(await api(`/api/quotes/${b.dataset.copyq}/duplicate`,'POST',{}));$('modal').close();}));$$('[data-deleteq]').forEach(b=>b.onclick=run(async()=>{if(!confirm('Delete this quotation? / 删除这份报价？'))return;await api('/api/quotes/'+b.dataset.deleteq,'DELETE');if(S.q.id===+b.dataset.deleteq)await newQuote();await history();}));};$('historySearch').oninput=draw;draw();}
async function lock(){await save();const action=S.q.locked?'unlock':'lock';adopt(await api(`/api/quotes/${S.q.id}/${action}`,'POST',{}));toast(action==='lock'?'Price and rule snapshot locked / 已锁定价格与规则快照':'Revision created; original stays locked / 已创建修订版，原报价保持锁定');}
async function exportsModal(){await save();if(!S.q.items.length)throw Error('Add items before export / 请先添加报价明细');modal(bi('Export quotation','导出报价'),`<div class="notice">${bi('Quotation layout · embedded cabinet drawings · English-first bilingual','报价版式 · 内嵌柜体示意图 · 英主中辅')}</div>${S.q.items.some(i=>(i.note&&!i.note_en)||(i.room_note&&!i.room_note_en))?'<div class="warning">Some custom notes have no English translation. Original text is preserved; edit the item to add English.<br>部分自定义备注缺少英文；将保留原文，可编辑明细补充英文。</div>':''}<div class="export-grid">${['customer','internal'].map(kind=>`<section class="export-card"><h3>${bi(kind==='customer'?'Customer copy':'Internal copy',kind==='customer'?'客户版':'内部版')}</h3><p>${kind==='customer'?'Quotation and editable calculations, without supply prices or profit.<br>报价及可重算公式，不含供货成本及毛利。':'Full calculation, material usage, cost and gross profit.<br>含计算明细、材料用量、成本及毛利。'}</p><div><button class="primary" data-export="${kind}:xlsx">Excel .xlsx</button><button data-export="${kind}:pdf">PDF</button><button data-print="${kind}">${bi('Print / preview','打印／预览')}</button></div></section>`).join('')}</div><p class="warning">${bi('Excel diagrams are embedded static previews. Re-export from this app after changing dimensions for updated pictures.','Excel图片为嵌入式静态示意图；修改尺寸后请在本软件重新导出以更新图片。')}</p>`);$$('[data-export]').forEach(b=>b.onclick=run(async()=>{const [kind,fmt]=b.dataset.export.split(':');b.disabled=true;const old=b.textContent;b.textContent='Exporting… / 导出中';try{const r=await api(`/api/quotes/${S.q.id}/export?kind=${kind}&fmt=${fmt}`);const a=document.createElement('a');a.href=r.url;a.download=r.name;a.click();toast('Export complete / 导出完成');}finally{b.disabled=false;b.textContent=old;}}));$$('[data-print]').forEach(b=>b.onclick=()=>window.open(`/print/${S.q.id}?kind=${b.dataset.print}`,'_blank','noopener'));}
function field(id,en,cn,value='',type='text'){return `<label>${bi(en,cn)}<input id="${id}" type="${type}" value="${esc(value)}"></label>`;}
function details(){const q=S.q;modal(bi('Quotation details & terms','报价详情与条款'),`<div class="two-cols">${field('dAddress','Project address','项目地址',q.address)}${field('dValid','Valid days','有效天数',q.valid_days,'number')}</div><div class="two-cols"><label>${bi('Notes (EN)','英文备注')}<textarea id="dNoteEn">${esc(q.note_en)}</textarea></label><label>${bi('Notes (CN)','中文备注')}<textarea id="dNote">${esc(q.note)}</textarea></label><label>${bi('Terms (EN)','英文条款')}<textarea id="dTermsEn">${esc(q.terms_en)}</textarea></label><label>${bi('Terms (CN)','中文条款')}<textarea id="dTerms">${esc(q.terms)}</textarea></label></div>`,[{text:bi('Save details','保存详情'),primary:true,action:async()=>{assertEditable();Object.assign(q,{address:val('dAddress'),valid_days:num('dValid'),note:val('dNote'),note_en:val('dNoteEn'),terms:val('dTerms'),terms_en:val('dTermsEn')});changed();await save();$('modal').close();}}]);}

// Management: all fields are owned and persisted by this standalone installation.
const tabs=[['materials','Materials','材料'],['extras','Add-ons','增项'],['rules','Rules & categories','规则／品类'],['names','Cabinet name glossary','柜体名称词库'],['rooms','Floors & rooms','楼层／区域'],['company','Company & terms','公司／条款'],['template','Template','模板'],['contacts','Customers & projects','客户／项目'],['backup','Backup','备份'],['advanced','Advanced config','高级配置']];
async function manage(tab='materials'){await save();const [raw,mats]=await Promise.all([api('/api/config'),api('/api/materials')]);S.config=raw.config;S.materials=mats.materials||mats;S.manageDirty=false;modal(bi('Manage your quotation studio','报价系统管理'),'<div class="tabs" id="manageTabs"></div><div id="manageBody"></div>');showTab(tab);}
function showTab(tab){
 if(S.manageDirty&&!confirm('Discard unsaved changes in this section? / 放弃当前分区未保存的修改？'))return;
 S.manageDirty=false;S.manageTab=tab;
 $('manageTabs').innerHTML=tabs.map(([key,en,cn])=>`<button data-tab="${key}" class="${key===tab?'active':''}">${bi(en,cn)}</button>`).join('');
 $$('[data-tab]').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));$('modalFooter').innerHTML='';drawManagementTab();
}
function orderButtons(path,index,count,extra=''){
 const common=`data-order-path="${esc(path)}" data-order-index="${index}" ${extra}`;
 return `<span class="order-actions"><button type="button" ${common} data-order-delta="-1" aria-label="Move up / 上移" title="Move up / 上移" ${index===0?'disabled':''}>↑</button><button type="button" ${common} data-order-delta="1" aria-label="Move down / 下移" title="Move down / 下移" ${index===count-1?'disabled':''}>↓</button></span>`;
}
function orderRows(path,count,index,extra=''){return `<span class="order-cell">${orderButtons(path,index,count,extra)}</span>`;}
function moveArrayItem(arr,index,delta){const target=index+delta;if(!Array.isArray(arr)||index<0||target<0||target>=arr.length)return false;[arr[index],arr[target]]=[arr[target],arr[index]];return true;}
function moveObjectItem(obj,index,delta,part){
 let entries=Object.entries(obj||{}),active=entries.map((x,i)=>({key:x[0],value:x[1],slot:i})).filter(x=>!part||(part==='body'?x.value?.part!=='door':x.value?.part===part));
 const target=index+delta;if(index<0||target<0||target>=active.length)return false;
 [active[index],active[target]]=[active[target],active[index]];
 const slots=entries.map((x,i)=>!part||(part==='body'?x[1]?.part!=='door':x[1]?.part===part)?i:-1).filter(i=>i>=0);
 slots.forEach((slot,i)=>entries[slot]=[active[i].key,active[i].value]);
 return entries.length?Object.fromEntries(entries):false;
}
function managementInputBindings(){
 const body=$('manageBody');
 $$('input,select,textarea',body).forEach(i=>i.addEventListener('input',()=>S.manageDirty=true));
 $$('[data-order-path]',body).forEach(b=>b.onclick=run(()=>{
  collectConfig();const path=b.dataset.orderPath.split('|');let parent=S.config;
  for(const key of path.slice(0,-1))parent=parent[key]??={};
  const key=path.at(-1),index=Number(b.dataset.orderIndex),delta=Number(b.dataset.orderDelta),part=b.dataset.orderPart||'';
  if(Array.isArray(parent[key]))moveArrayItem(parent[key],index,delta);
  else if(parent[key]&&typeof parent[key]==='object'){
   const next=moveObjectItem(parent[key],index,delta,part);if(!next)return;parent[key]=next;
   if(path.join('|')==='meta|price_modes'){
    const english=S.config.meta.price_modes_en||{};
    S.config.meta.price_modes_en=Object.fromEntries(Object.keys(next).map(k=>[k,english[k]]).filter(x=>x[1]!==undefined));
   }
  }else return;
  S.manageDirty=true;drawManagementTab();
 }));
}
function drawManagementTab(){
 const tab=S.manageTab,draw={materials:materialTab,extras:extrasTab,rules:rulesTab,names:cabinetNamesTab,rooms:roomsTab,company:companyTab,template:templateTab,contacts:contactsTab,backup:backupTab,advanced:advancedTab}[tab];
 const result=draw();if(tab==='contacts')return result;
 managementInputBindings();return result;
}
function configSaveButton(collect){
 $('modalFooter').innerHTML='';const b=document.createElement('button');b.id='saveConfig';b.className='primary';b.innerHTML=bi('Save changes','保存修改');
 b.onclick=run(async()=>{collect();const r=await api('/api/config','PUT',{config:S.config});r.bootstrap.ui_order=S.config.ui_order||{};S.order=r.bootstrap.ui_order;refreshBoot(r.bootstrap);if(S.q)set('mode',S.q.mode);await syncContactDatalists();S.manageDirty=false;await recompute();toast('Configuration saved independently / 配置已独立保存，重启后保留');});$('modalFooter').appendChild(b);
}
function dataInput(path,v,type='text',wide=false){return `<input data-path="${esc(path)}" value="${esc(v??'')}" type="${type}" class="${wide?'wide':''}" ${type==='number'?'step="any" min="0"':''}>`;}
function dataCheck(path,v){return `<input data-path="${esc(path)}" type="checkbox" ${v!==false?'checked':''}>`;}
function collectConfig(){for(const i of $$('[data-path]',$('manageBody'))){const keys=i.dataset.path.split('|');let o=S.config;for(const k of keys.slice(0,-1)){o=o[k]??=(/^\d+$/.test(k)?[]:{});}o[keys.at(-1)]=i.type==='checkbox'?i.checked:i.type==='number'?Number(i.value):i.value;}}
function table(heads,rows){return `<div class="manage-table-wrap"><table class="manage-table"><thead><tr>${heads.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>'<tr>'+row.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')}</tbody></table></div>`;}
function orderedMaterialRows(){
  const catRank=new Map(S.config.categories.map((c,i)=>[c.key,i]));
  return S.materials.filter(m=>catRank.has(m.cat_key)).slice().sort((a,b)=>{
  const cat=(catRank.get(a.cat_key)??999)-(catRank.get(b.cat_key)??999);if(cat)return cat;
  const ad=S.config.prices[a.cat_key]?.[a.mat_key],bd=S.config.prices[b.cat_key]?.[b.mat_key];
  const part=(ad?.part==='door'?1:0)-(bd?.part==='door'?1:0);if(part)return part;
  return Object.keys(S.config.prices[a.cat_key]||{}).indexOf(a.mat_key)-Object.keys(S.config.prices[b.cat_key]||{}).indexOf(b.mat_key);
 });
}
function materialTab(){
 const rows=orderedMaterialRows();
 const heads=[bi('Order','排序'),bi('Material / category','材料／品类'),bi('English / Chinese name','英／中文名称'),bi('Quote / cost (RM)','报价／成本'),bi('Supplier','供应商'),bi('Stock / safety stock','库存／安全库存'),bi('Enabled','启用'),bi('Actions','操作')];
 $('manageBody').innerHTML=`<div class="manage-toolbar"><p>Blank prices use your price list. Disabled materials remain in history.<br>价格留空使用价格表；停用材料仍保留历史记录。</p><button id="newMaterial">＋ ${bi('New material','新增材料')}</button></div>`+table(heads,rows.map(m=>{
  const priceItems=S.config.prices[m.cat_key]||{},samePart=Object.entries(priceItems).filter(([,entry])=>m.part==='door'?entry.part==='door':entry.part!=='door'),index=samePart.findIndex(([key])=>key===m.mat_key),path=`prices|${m.cat_key}`,order=orderRows(path,samePart.length,index,`data-order-key="${esc(m.mat_key)}" data-order-part="${m.part==='door'?'door':'body'}"`);
   return [order,esc(m.code)+`<small>${esc(m.cat_key)} · ${esc(m.part)}</small>`,`<input data-mid="${m.id}" data-mfield="name_en" value="${esc(m.name_en)}" class="wide"><input data-mid="${m.id}" data-mfield="name" value="${esc(m.name)}" class="wide">`,`<input data-mid="${m.id}" data-mfield="quote_price" type="number" min="0" step="0.01" value="${m.quote_price??''}" placeholder="${m.default_quote}"><input data-mid="${m.id}" data-mfield="cost_price" type="number" min="0" step="0.01" value="${m.cost_price??''}" placeholder="${m.default_cost}">`,`<input data-mid="${m.id}" data-mfield="supplier" value="${esc(m.supplier)}">`,`<input data-mid="${m.id}" data-mfield="stock_qty" type="number" value="${m.stock_qty}"><input data-mid="${m.id}" data-mfield="safety_stock" type="number" value="${m.safety_stock}">${m.stock_alert?'<small>Low stock / 低库存</small>':''}`,`<input data-mid="${m.id}" data-mfield="enabled" type="checkbox" ${m.enabled?'checked':''}>`,`<button data-save-material="${m.id}">${bi('Save','保存')}</button><button data-reset-material="${m.id}">${bi('Reset price','恢复单价')}</button><button class="danger" data-delete-material="${m.id}">${bi('Delete','删除')}</button>`];
  }));
  $$('[data-save-material]').forEach(b=>b.onclick=run(async()=>{const id=b.dataset.saveMaterial,p={};$$(`[data-mid="${id}"]`).forEach(i=>p[i.dataset.mfield]=i.type==='checkbox'?i.checked:i.type==='number'?(i.value===''?null:+i.value):i.value);await api('/api/materials/'+id,'PUT',p);S.manageDirty=false;refreshBoot(await api('/api/bootstrap'));set('mode',S.q.mode);await recompute();toast('Material saved / 材料已保存');}));
  $$('[data-delete-material]').forEach(b=>b.onclick=run(async()=>{if(!confirm('Remove this material from future quotations? Existing quotations keep their saved material. / 从后续报价中删除此材料？既有报价保留原材料记录。'))return;const id=b.dataset.deleteMaterial;await api('/api/materials/'+id,'DELETE');const item=S.materials.find(m=>String(m.id)===id);if(item)item.enabled=false;const enabled=$$(`[data-mid="${id}"][data-mfield="enabled"]`)[0];if(enabled)enabled.checked=false;S.manageDirty=true;refreshBoot(await api('/api/bootstrap'));await recompute();toast('Material removed from selection / 材料已从新报价选项中移除');}));
  $$('[data-reset-material]').forEach(b=>b.onclick=run(async()=>{await api(`/api/materials/${b.dataset.resetMaterial}/reset`,'POST',{});S.manageDirty=false;await manage('materials');await recompute();}));$('newMaterial').onclick=()=>recordForm('material');configSaveButton(collectConfig);
}
 function recordForm(kind,selectedCategory=''){const back=kind==='material'?'materials':'contacts';const categories=S.config.categories.filter(c=>c.enabled!==false);modal(bi(kind==='material'?'New material':kind==='customer'?'New customer':'New project',kind==='material'?'新增材料':kind==='customer'?'新增客户':'新增项目'),`<div class="two-cols">${field('rNameEn',kind==='material'?'English name':'Name',kind==='material'?'英文名称':'名称')}${field('rName',kind==='material'?'Chinese name':'Phone / address',kind==='material'?'中文名称':'电话／地址')}</div>${kind==='material'?`<div class="three-cols"><label>${bi('Category','品类')}<select id="rCat">${categories.map(c=>`<option value="${esc(c.key)}" ${c.key===selectedCategory?'selected':''}>${esc(c.name_en+' / '+c.name)}</option>`).join('')}</select></label><label>${bi('Part','部件')}<select id="rPart"><option value="body">Carcass / 柜体</option><option value="door">Door / 柜门</option></select></label><label>${bi('Unit','单位')}<select id="rUnit"><option value="ft2">ft²</option><option value="ft">ft</option><option value="pcs">pcs / 个</option></select></label>${field('rPrice','Quote price','报价',0,'number')}${field('rCost','Supply cost','成本',0,'number')}</div>`:''}`,[{text:bi('Create','创建'),primary:true,action:async()=>{if(!val('rNameEn').trim())throw Error('Enter a name / 请填写名称');if(kind==='material')await api('/api/materials','POST',{cat_key:val('rCat'),part:val('rPart'),name:val('rName'),name_en:val('rNameEn'),unit:val('rUnit'),quote_price:num('rPrice'),cost_price:num('rCost')});else await api('/api/'+(kind==='customer'?'customers':'projects'),'POST',{name:val('rNameEn'),phone:kind==='customer'?val('rName'):'',address:kind==='project'?val('rName'):''});S.manageDirty=false;refreshBoot(await api('/api/bootstrap'));set('mode',S.q.mode);await manage(back);}}]);}
function extrasTab(){
 const items=S.config.extras.items;
  $('manageBody').innerHTML=`<div class="manage-toolbar"><p>All add-ons are editable. Delete disables the item for new quotations; saved rows keep their pricing and can be restored.<br>增项均可修改；删除会停用新报价选项，既有明细仍按原价计算，也可重新启用。</p><button id="newExtra">＋ ${bi('New add-on','新增增项')}</button></div>`+table([bi('Order','排序'),bi('Name EN / CN','英／中文名'),bi('Price / unit','单价／单位'),bi('Basis','计价依据'),bi('Applies to categories','适用品类'),bi('Enabled','启用'),bi('Actions','操作')],items.map((e,n)=>{const p=`extras|items|${n}|`;return [orderRows('extras|items',items.length,n),dataInput(p+'name_en',e.name_en,'text',true)+dataInput(p+'name',e.name,'text',true),dataInput(p+'price',e.price,'number')+dataInput(p+'unit',e.unit),`<select data-path="${p}basis">${[['qty','Quantity / 数量'],['length','Length / 长度 ft'],['area','Area / 面积 ft²']].map(([v,t])=>`<option value="${v}" ${(e.basis||'qty')===v?'selected':''}>${t}</option>`).join('')}</select>`,`<div class="category-checklist" data-ecats="${n}">${S.config.categories.map(c=>`<label class="category-option"><input type="checkbox" data-catvalue="${esc(c.key)}" ${!e.cats||e.cats.includes(c.key)?'checked':''}><span>${bi(c.name_en,c.name)}</span></label>`).join('')}</div>`,dataCheck(p+'enabled',e.enabled),`<button class="danger" data-disable-extra="${esc(e.key)}">${bi('Delete','删除')}</button>`];}));
  $('manageBody').querySelector('.manage-table-wrap').classList.add('manage-table-wrap--extras');
  $$('[data-disable-extra]').forEach(b=>b.onclick=()=>{if(!confirm('Remove this add-on from future quotations? Existing quotation rows keep their pricing. / 从新报价中移除此增项？既有报价仍按原价计算。'))return;collectConfig();const e=items.find(x=>x.key===b.dataset.disableExtra);e.enabled=false;drawManagementTab();S.manageDirty=true;});
 $('newExtra').onclick=()=>{collectConfig();items.push({key:'extra_'+Date.now(),name:'新增增项',name_en:'New add-on',price:0,unit:'pcs',basis:'qty',cats:S.config.categories.map(c=>c.key),enabled:true});drawManagementTab();S.manageDirty=true;};
 configSaveButton(()=>{collectConfig();$$('[data-ecats]').forEach(d=>items[+d.dataset.ecats].cats=$$('input:checked',d).map(i=>i.dataset.catvalue));S.config.led.price_per_m=items.find(e=>e.key==='led')?.price??S.config.led.price_per_m;S.config.led.power_price=items.find(e=>e.key==='led_power')?.price??S.config.led.power_price;S.config.led.sensor_price=items.find(e=>e.key==='led_sensor')?.price??S.config.led.sensor_price;});
}
function rulesTab(){
 const modes=S.config.meta.price_modes||{},modeKeys=Object.keys(modes);
 const modeRows=modeKeys.map((k,n)=>[orderRows('meta|price_modes',modeKeys.length,n),bi(S.config.meta.price_modes_en?.[k]||k,modes[k]||k)]);
 const categories=S.config.categories;
  const categoryRows=categories.map((c,n)=>{const p=`categories|${n}|`;return [orderRows('categories',categories.length,n),dataInput(p+'name_en',c.name_en,'text',true)+dataInput(p+'name',c.name,'text',true),`<select data-path="${p}measure">${[['area','Area ft² / 面积'],['length','Length ft / 长度'],['pcs','Quantity / 数量']].map(([k,v])=>`<option value="${k}" ${c.measure===k?'selected':''}>${v}</option>`).join('')}</select>`,dataInput(p+'std_depth_mm',c.std_depth_mm||0,'number'),dataInput(p+'min_height_ft',c.min_height_ft||0,'number'),dataInput(p+'default_height_mm',c.default_height_mm||0,'number'),dataInput(p+'std_height_ft',c.std_height_ft||0,'number'),dataCheck(p+'enabled',c.enabled),`<button data-category-materials="${esc(c.key)}" ${c.enabled===false?'disabled':''}>${bi('＋ Material','新增材料')}</button><button class="danger" data-delete-category="${esc(c.key)}" ${c.enabled!==false&&categories.filter(x=>x.enabled!==false).length===1?'disabled':''}>${bi('Delete','删除')}</button>`];});
  $('manageBody').innerHTML=`<div class="notice">${bi('Default rules preserve the original calculation. Save the category, then add its own materials. Deleted categories used by saved quotations remain archived.','默认规则沿用原算法。先保存品类，再为该品类新增材料；旧报价使用过的已删除品类会保留为历史归档。')}</div><h3>${bi('Quotation price strategy order','报价策略选项顺序')}</h3>`+table([bi('Order','排序'),bi('Option','选项')],modeRows)+`<h3>${bi('Category order','品类选项顺序')}</h3>`+table([bi('Order','排序'),bi('Category EN / CN','品类英／中文'),bi('Measure','计价方式'),bi('Standard depth mm','标准深度'),bi('Minimum height ft','最低计价高'),bi('Default height mm','默认高度'),bi('Standard height ft','标准高度'),bi('Enabled','启用'),bi('Actions','操作')],categoryRows)+`<div class="three-cols"><label>${bi('Non-standard multiplier','非标系数')}${dataInput('meta|nonstd_factor',S.config.meta.nonstd_factor,'number')}</label><label>${bi('Height tolerance (ft)','高度容差')}${dataInput('meta|height_tol_ft',S.config.meta.height_tol_ft,'number')}</label><label>${bi('Millimetres per foot','每英尺毫米数')}${dataInput('meta|mm_per_ft',S.config.meta.mm_per_ft,'number')}</label></div><button id="newCategory">＋ ${bi('New category','新增品类')}</button>`;
  $$('[data-category-materials]').forEach(b=>b.onclick=run(async()=>{collectConfig();if(S.config.categories.find(c=>c.key===b.dataset.categoryMaterials)?.enabled===false)throw Error('Enable this category before adding materials / 请先启用品类，再新增材料');await api('/api/config','PUT',{config:S.config});S.manageDirty=false;refreshBoot(await api('/api/bootstrap'));await manage('materials');recordForm('material',b.dataset.categoryMaterials);}));
  $$('[data-delete-category]').forEach(b=>b.onclick=()=>{if(!confirm('Delete this category? Saved quotations will keep an archived copy when needed. / 删除此品类？既有报价需要时会保留历史归档。'))return;collectConfig();const key=b.dataset.deleteCategory;S.config.categories=S.config.categories.filter(c=>c.key!==key);delete S.config.prices[key];for(const e of S.config.extras.items||[])if(e.cats){e.cats=e.cats.filter(k=>k!==key);if(!e.cats.length)e.enabled=false;}drawManagementTab();S.manageDirty=true;});
  $('newCategory').onclick=()=>{collectConfig();const sources=S.config.categories.filter(c=>c.enabled!==false);modal(bi('New category','新增品类'),`<div class="two-cols">${field('newCatEn','English name','英文名称','New category')}${field('newCatZh','Chinese name','中文名称','新增品类')}</div><label>${bi('Copy materials from','复制材料模板')}<select id="newCatSource"><option value="">${bi('Start with a new material','从新材料开始')}</option>${sources.map(c=>`<option value="${esc(c.key)}">${esc(c.name_en+' / '+c.name)}</option>`).join('')}</select></label>`,[{text:bi('Create category','创建品类'),primary:true,action:async()=>{const key='category_'+Date.now(),source=S.config.categories.find(c=>c.key===val('newCatSource'));S.config.categories.push({key,name:val('newCatZh').trim()||'新增品类',name_en:val('newCatEn').trim()||'New category',group:source?.group||'cabinet',measure:source?.measure||'area',std_depth_mm:source?.std_depth_mm||600,default_height_mm:source?.default_height_mm||2400,min_height_ft:source?.min_height_ft||0,std_height_ft:source?.std_height_ft||0,enabled:true});S.config.prices[key]=source?clone(S.config.prices[source.key]):{standard:{label:'新材料',label_en:'New material',part:'body',unit:'ft2',supply:0,market:[0,0]}};const r=await api('/api/config','PUT',{config:S.config});S.config=r.bootstrap.config||S.config;refreshBoot(r.bootstrap);S.manageDirty=false;await manage('materials');if(!source)recordForm('material',key);}}]);};configSaveButton(collectConfig);
}
function cabinetNamesTab(){
 const terms=S.config.cabinet_name_glossary||{};S.config.cabinet_name_glossary=terms;
 const rows=Object.entries(terms).map(([zh,en],i)=>[`<input data-glossary-zh="${i}" value="${esc(zh)}" placeholder="中文名称">`,`<input data-glossary-en="${i}" value="${esc(en)}" placeholder="English name">`,`<button class="danger" data-delete-glossary="${i}">${bi('Delete','删除')}</button>`]);
 $('manageBody').innerHTML=`<div class="notice">${bi('Enter one Chinese–English cabinet term per row. Export fills the other language; unknown terms are preserved unchanged.','每行维护一个中英柜体词条；导出时补出另一语言，未收录名称原样保留。')}</div>`+table([bi('Chinese','中文'),bi('English','英文'),bi('Actions','操作')],rows)+`<button id="addGlossary">＋ ${bi('Add term','新增词条')}</button>`;
 $$('[data-delete-glossary]').forEach(b=>b.onclick=()=>{collectGlossary();const i=+b.dataset.deleteGlossary,key=Object.keys(S.config.cabinet_name_glossary)[i];delete S.config.cabinet_name_glossary[key];S.manageDirty=true;drawManagementTab();});
 $('addGlossary').onclick=()=>{collectGlossary();S.config.cabinet_name_glossary['新词条']='New term';S.manageDirty=true;drawManagementTab();};
 configSaveButton(()=>collectGlossary());
}
function collectGlossary(){
 const glossary={};$$('[data-glossary-zh]').forEach(i=>{const n=i.dataset.glossaryZh,en=$(`[data-glossary-en="${n}"]`)?.value.trim(),zh=i.value.trim();if(zh&&en)glossary[zh]=en;});S.config.cabinet_name_glossary=glossary;
}
function roomsTab(){
 S.config.floors??=clone(S.boot.floors);const floors=S.config.floors,rooms=S.config.rooms;
  $('manageBody').innerHTML='<h3>'+bi('Floors','楼层')+'</h3>'+table([bi('Order','排序'),bi('Code','编码'),bi('English name','英文名'),bi('Chinese name','中文名'),bi('Actions','操作')],floors.map((f,n)=>[orderRows('floors',floors.length,n),dataInput(`floors|${n}|code`,f.code),dataInput(`floors|${n}|name_en`,f.name_en),dataInput(`floors|${n}|name`,f.name||''),`<button class="danger" data-delete-floor="${n}">${bi('Delete','删除')}</button>`]))+`<button id="newFloor">＋ ${bi('Add floor','新增楼层')}</button><h3 style="margin-top:22px">${bi('Rooms','区域')}</h3>`+table([bi('Order','排序'),bi('Chinese name','中文名'),bi('English name','英文名'),bi('Actions','操作')],rooms.map((r,n)=>[orderRows('rooms',rooms.length,n),dataInput(`rooms|${n}|name`,r.name),dataInput(`rooms|${n}|name_en`,r.name_en),`<button class="danger" data-delete-room="${n}" ${rooms.length===1?'disabled':''}>${bi('Delete','删除')}</button>`]))+`<button id="newRoom">＋ ${bi('Add room','新增区域')}</button>`;
  $$('[data-delete-floor]').forEach(b=>b.onclick=()=>{if(!confirm('Delete this floor option? Existing quotation rows keep their floor code. / 删除此楼层选项？既有报价明细保留原楼层编码。'))return;collectConfig();S.config.floors.splice(+b.dataset.deleteFloor,1);drawManagementTab();S.manageDirty=true;});
  $$('[data-delete-room]').forEach(b=>b.onclick=()=>{if(!confirm('Delete this room option? Existing quotation rows keep their room name. / 删除此区域选项？既有报价明细保留原区域名称。'))return;collectConfig();S.config.rooms.splice(+b.dataset.deleteRoom,1);drawManagementTab();S.manageDirty=true;});
 $('newFloor').onclick=()=>{collectConfig();S.config.floors.push({code:'L'+(S.config.floors.length+1),name_en:'New floor',name:'新楼层'});drawManagementTab();S.manageDirty=true;};
 $('newRoom').onclick=()=>{collectConfig();S.config.rooms.push({name:'新区域',name_en:'New room'});drawManagementTab();S.manageDirty=true;};configSaveButton(collectConfig);
}
function companyTab(){
 const co=S.config.company,terms=S.config.remark.items||[],notes=S.config.remark.notes||[];
  $('manageBody').innerHTML='<div class="two-cols">'+[['name','Company name','公司名称'],['name_cn','Company name (CN)','公司中文名'],['address','Address','地址'],['address_cn','Address (CN)','中文地址'],['mobile','Telephone','电话'],['email','Email','邮箱'],['title','Quotation title','报价标题'],['title_cn','Title (CN)','中文标题'],['greeting','Opening sentence','开头说明'],['greeting_cn','Opening sentence (CN)','中文说明']].map(([k,en,cn])=>`<label>${bi(en,cn)}${dataInput('company|'+k,co[k])}</label>`).join('')+'</div>'+`<label>${bi('Upload company logo','上传公司Logo')}<input id="logoFile" type="file" accept="image/png,image/jpeg,image/webp"></label><h3 style="margin-top:22px">${bi('Quotation terms order','报价条款顺序')}</h3>`+table([bi('Order','排序'),bi('Label','标题'),bi('English','英文'),bi('Chinese','中文'),bi('Actions','操作')],terms.map((r,n)=>[orderRows('remark|items',terms.length,n),dataInput(`remark|items|${n}|label`,r.label),dataInput(`remark|items|${n}|en`,r.en,'text',true),dataInput(`remark|items|${n}|cn`,r.cn,'text',true),`<button class="danger" data-delete-term="${n}">${bi('Delete','删除')}</button>`]))+`<button id="newTerm">＋ ${bi('Add term','新增条款')}</button><h3 style="margin:22px 0 12px">${bi('Quotation notes order','报价备注顺序')}</h3>`+table([bi('Order','排序'),bi('English','英文'),bi('Chinese','中文')],notes.map((r,n)=>[orderRows('remark|notes',notes.length,n),dataInput(`remark|notes|${n}|en`,r.en,'text',true),dataInput(`remark|notes|${n}|cn`,r.cn,'text',true)]));
  $$('[data-delete-term]').forEach(b=>b.onclick=()=>{if(!confirm('Delete this quotation term? / 删除此报价条款？'))return;collectConfig();terms.splice(+b.dataset.deleteTerm,1);drawManagementTab();S.manageDirty=true;});
  $('newTerm').onclick=()=>{collectConfig();terms.push({no:String(terms.length+1),label:'New term',en:'',cn:''});drawManagementTab();S.manageDirty=true;};$('logoFile').onchange=run(async e=>{const data=await readFile(e.target.files[0]);await api('/api/logo','POST',{data});const r=await api('/api/config');S.config.company.logo=r.config.company.logo;toast('Logo uploaded / Logo已上传');});configSaveButton(collectConfig);
}
function templateTab(){S.config.template??={column_widths:{A:5.5,B:22,C:26,D:36,E:20,F:12,G:7,H:7,I:16,J:30}};S.config.totals??={};$('manageBody').innerHTML=`<div class="notice">${bi('Stationery, column order and drawing sizes follow the current quotation layout. Adjust widths and drawing size below.','抬头与列顺序沿用当前报价版式；可在下方调整列宽和图片尺寸。')}</div><div class="three-cols">${Object.entries(S.config.template.column_widths).map(([c,v])=>`<label>${bi('Column '+c+' width','列宽')}${dataInput('template|column_widths|'+c,v,'number')}</label>`).join('')}<label>${bi('Drawing width (px)','图片宽度')}${dataInput('illustration|width_px',S.config.illustration.width_px,'number')}</label><label>${bi('Drawing height (px)','图片高度')}${dataInput('illustration|height_px',S.config.illustration.height_px,'number')}</label></div><label>${dataCheck('totals|show_discount_row',!!S.config.totals.show_discount_row)}${bi('Show discount below product total','报价页显示折扣')}</label><label>${dataCheck('totals|show_deposit_rows',!!S.config.totals.show_deposit_rows)}${bi('Show deposit and balance below product total','报价页显示定金与余款')}</label><p class="warning">${bi('Default shows the product total only. Full payment calculations remain in the summary sheet.','默认仅显示产品合计；完整付款计算保留在汇总表。')}</p>`;configSaveButton(collectConfig);}
function orderedContactRows(rows,type){
 S.config.ui_order??={};S.config.ui_order.contacts??={};const saved=S.config.ui_order.contacts[type]||[],present=new Set(rows.map(x=>Number(x.id))),ids=saved.map(Number).filter((id,i)=>present.has(id)&&saved.indexOf(id)===i);
 for(const r of rows)if(!ids.includes(Number(r.id)))ids.push(Number(r.id));
 S.config.ui_order.contacts[type]=ids;const rank=new Map(ids.map((id,i)=>[id,i]));return rows.slice().sort((a,b)=>rank.get(Number(a.id))-rank.get(Number(b.id)));
}
function orderedContactsFromBoot(rows,type){
 const saved=S.boot?.ui_order?.contacts?.[type]||[],rank=new Map(saved.map((id,i)=>[Number(id),i]));
 return rows.map((r,i)=>({r,i,rank:rank.has(Number(r.id))?rank.get(Number(r.id)):Infinity})).sort((a,b)=>a.rank-b.rank||a.i-b.i).map(x=>x.r);
}
async function syncContactDatalists(){
 try{const [cr,pr]=await Promise.all([api('/api/customers'),api('/api/projects')]);const customers=orderedContactsFromBoot(cr.customers||cr,'customers'),projects=orderedContactsFromBoot(pr.projects||pr,'projects');
  $('customerNames').innerHTML=customers.map(c=>option(c.name,c.name)).join('');$('projectNames').innerHTML=projects.map(p=>option(p.name,p.name)).join('');
 }catch(e){console.error(e);}
}
async function contactsTab(){
 const [cr,pr]=await Promise.all([api('/api/customers'),api('/api/projects')]);
 const customers=orderedContactRows(cr.customers||cr,'customers'),projects=orderedContactRows(pr.projects||pr,'projects');
 const records=[...customers.map((x,i)=>({...x,type:'customers',orderIndex:i,orderCount:customers.length})),...projects.map((x,i)=>({...x,type:'projects',orderIndex:i,orderCount:projects.length}))];
 $('manageBody').innerHTML=`<div class="manage-toolbar"><h3>${bi('Customers & projects','客户与项目')}</h3><div><button id="newCustomer">＋ ${bi('Customer','客户')}</button><button id="newProject">＋ ${bi('Project','项目')}</button></div></div>`+table([bi('Order','排序'),bi('Type','类型'),bi('Name','名称'),bi('Contact / address','联系／地址'),bi('Actions','操作')],records.map((r,i)=>[orderRows(`ui_order|contacts|${r.type}`,r.orderCount,r.orderIndex,`data-order-key="${r.id}"`),bi(r.type==='customers'?'Customer':'Project',r.type==='customers'?'客户':'项目'),esc(r.name),esc(r.phone||r.address||r.email||''),`<button data-contact-edit="${i}">${bi('Edit','修改')}</button><button class="danger" data-contact-delete="${i}">${bi('Delete','删除')}</button>`]));
 $('newCustomer').onclick=()=>recordForm('customer');$('newProject').onclick=()=>recordForm('project');
 $$('[data-contact-delete]').forEach(b=>b.onclick=run(async()=>{const r=records[+b.dataset.contactDelete];if(!confirm('Delete this directory entry? Existing quotations are preserved. / 删除此通讯录记录？既有报价将保留。'))return;await api(`/api/${r.type}/${r.id}`,'DELETE');await contactsTab();}));
 $$('[data-contact-edit]').forEach(b=>b.onclick=()=>{const r=records[+b.dataset.contactEdit];modal(bi('Edit directory entry','修改客户／项目'),`<div class="two-cols">${field('contactName','Name','名称',r.name)}${field('contactPhone','Telephone','电话',r.phone||'')}${field('contactEmail','Email','邮箱',r.email||'')}${field('contactAddress','Address','地址',r.address||'')}</div><label>${bi('Note','备注')}<textarea id="contactNote">${esc(r.note||'')}</textarea></label>`,[{text:bi('Save changes','保存修改'),primary:true,action:async()=>{if(!val('contactName').trim())throw Error('Enter a name / 请填写名称');await api(`/api/${r.type}/${r.id}`,'PUT',{name:val('contactName'),phone:val('contactPhone'),email:val('contactEmail'),address:val('contactAddress'),note:val('contactNote')});S.manageDirty=false;await manage('contacts');toast('Directory entry saved / 客户／项目已保存');}}]);});
 configSaveButton(()=>{});managementInputBindings();
}
function backupTab(){$('manageBody').innerHTML=`<div class="notice">${bi('Your complete database, prices and uploaded company logo in one backup file. Management settings and quote data are saved automatically in the application folder\\workspace-data and retained after closing the app.','一个文件备份所有报价、客户、价格、配置及上传Logo。管理设置和报价数据也会自动保存在程序目录\\workspace-data，关闭软件后仍会保留。')}</div><p><a href="/api/backup" download><button class="primary">${bi('Download full backup','下载完整备份')}</button></a></p><h3 style="margin:24px 0 12px">${bi('Restore backup','恢复备份')}</h3><input id="backupFile" type="file" accept=".json"><p class="warning">${bi('Restoring replaces the current database. A rollback backup is created automatically before restoration.','恢复将替换当前数据库；恢复前会自动保存一份可回退备份。')}</p><button id="restoreBtn">${bi('Restore selected backup','恢复所选备份')}</button><h3 style="margin:24px 0 12px">${bi('Application','应用')}</h3><button id="quitBtn">${bi('Save & quit application','保存并退出应用')}</button>`;$('restoreBtn').onclick=run(async()=>{const f=$('backupFile').files[0];if(!f)throw Error('Select a backup file / 请选择备份文件');if(!confirm('Replace current data with the selected backup? / 确认用所选备份替换当前数据？'))return;await api('/api/restore','POST',JSON.parse(await f.text()));S.manageDirty=false;localStorage.removeItem('vouguer-next-v4-quote');location.reload();});$('quitBtn').onclick=run(async()=>{await save();await api('/api/shutdown','POST',{});$('modalBody').innerHTML='<div class="empty">Application stopped. You may close this window.<br>应用已停止，可以关闭此窗口。</div>';$('modalFooter').innerHTML='';});}
function advancedTab(){$('manageBody').innerHTML=`<p class="notice">${bi('Full independent business configuration. Add, edit, remove or restore fields here; stable keys keep historical quotations readable.','完整独立业务配置，可新增、修改、删除及恢复字段；保留历史引用编码可保证旧报价可读。')}</p><textarea class="raw-editor" id="configJSON" spellcheck="false">${esc(JSON.stringify(S.config,null,2))}</textarea>`;configSaveButton(()=>{S.config=JSON.parse(val('configJSON'));});}
function readFile(f){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(Error('Read failed / 读取失败'));r.readAsDataURL(f);});}
function drawing(){let candidates=[];modal(bi('Drawing to quotation','图纸生成报价草稿'),`<div class="notice">${bi('Copy an image and press Ctrl+V here, or upload a file. Dimensions are extracted locally; confirm cabinet, height and material before adding. Flat plans do not define these reliably.','可在此按Ctrl+V粘贴图片，或选择文件。本机识别尺寸，添加前请确认柜体、高度和材料；平面图未明确的信息不会自动猜测。')}</div><div class="drawing-grid"><div><label>${bi('Image / PDF / ASCII DXF','图片／PDF／ASCII DXF')}<input id="drawingFile" type="file" accept="image/png,image/jpeg,image/webp,.pdf,.dxf"></label><div class="drawing-preview" id="drawingPreview">${bi('Your drawing appears here','在这里查看图纸')}</div><p id="drawingEngine"></p></div><div><label>${bi('Recognized or pasted dimension text','识别结果／粘贴尺寸文本')}<textarea id="drawingText" placeholder="2400 × 2400 × 600 mm\n1200 × 600 mm"></textarea></label><button id="parseDrawing">${bi('Find dimensions','提取尺寸')}</button><div class="number-chips" id="dimensionNumbers"></div><div id="dimensionCandidates"></div><p class="warning">${bi('Two-number plan dimensions mean length × depth. Set height yourself in the entry form. All dimensions shown in mm.','平面图两段尺寸按长×深处理，高度在录入表单手填。候选尺寸统一为mm。')}</p></div></div>`);const draw=r=>{candidates=r.candidates||[];set('drawingText',r.text);$('drawingEngine').textContent=r.engine||'';if(r.preview)$('drawingPreview').innerHTML=`<img src="${r.preview}" alt="Drawing preview / 图纸预览">`;$('dimensionCandidates').innerHTML=candidates.map((c,i)=>`<div class="candidate"><div><strong>${c.length_mm} × ${c.height_mm||'?'} × ${c.depth_mm} mm</strong><p>${esc(c.source)}</p></div><button data-candidate="${i}">${bi('Use dimensions','填入尺寸')}</button></div>`).join('')||'<p>No dimension pair found. Select a number below or edit the text.<br>未找到尺寸组合，可选择单个数字或编辑文本。</p>';$('dimensionNumbers').innerHTML=(r.numbers||[]).map(n=>`<button data-number="${esc(n)}">${esc(n)}</button>`).join('');$$('[data-candidate]').forEach(b=>b.onclick=()=>{const c=candidates[+b.dataset.candidate];set('unit','mm');S.unit='mm';set('length',c.length_mm);set('depth',c.depth_mm);set('height',c.height_mm||'');$('modal').close();preview();$('height').focus();toast('Dimensions filled; confirm height and material / 尺寸已填入，请确认高度及材料');});$$('[data-number]').forEach(b=>b.onclick=()=>{const field=prompt('Assign to L, H or D? / 填入 L长、H高或D深？','L');const id={L:'length',H:'height',D:'depth'}[(field||'').toUpperCase()];if(id){set(id,Number(b.dataset.number)/factors[val('unit')]);toast('Dimension assigned / 尺寸已指定');preview();}});};const processFile=run(async f=>{if(!f)return;$('drawingEngine').textContent='Recognizing locally… / 正在本机识别';draw(await api('/api/drawing','POST',{name:f.name,data:await readFile(f)}));});drawingPasteHandler=processFile;$('parseDrawing').onclick=run(async()=>draw(await api('/api/drawing','POST',{text:val('drawingText')})));$('drawingFile').onchange=run(async e=>processFile(e.target.files[0]));}
function help(){modal(bi('Work faster','快捷操作'),table([bi('Shortcut','快捷键'),bi('Action','作用')],[['Enter / Ctrl+Enter',bi('Add or update quotation item','新增或保存行')],['Ctrl+S',bi('Save quotation','保存报价')],['Ctrl+E',bi('Export','导出')],['Ctrl+Z',bi('Undo item changes','撤销明细修改')],['Ctrl+D',bi('Duplicate selected items','复制所选行')],['Alt+L / H / D',bi('Focus dimension field','定位长／高／深')],['Ctrl+V',bi('Paste a drawing image in Drawing, or paste L × H × D dimensions','图纸录入粘贴图片，也可粘贴长×高×深尺寸')],['Double click / 双击',bi('Edit an existing item','回填修改')]])+'<div class="notice" style="margin-top:20px">Whole-House Quotation Studio 1.1 · locally stored data; configure your own catalogue and prices.<br>版本1.1，本机保存报价数据；请在管理页面配置自己的材料与价格。</div>');}
function bind(){const actions={newBtn:newQuote,manageBtn:async()=>{await save();location.href='/management.html';},historyBtn:history,exportBtn:exportsModal,drawingBtn:drawing,detailsBtn:details,lockBtn:lock,helpBtn:help,resetBtn:resetEntry,addRoomBtn:addRoomInstance,cancelEdit:resetEntry,demoBtn:loadDemo,orderChoicesBtn:openChoiceOrder};for(const [id,fn] of Object.entries(actions))$(id).onclick=run(fn);watchCatalogueOrder();$('closeModal').onclick=closeModal;$('modal').addEventListener('cancel',e=>{e.preventDefault();closeModal();});$('entryForm').onsubmit=run(e=>{e.preventDefault();addItem();});$$('input,select,textarea',$('entryForm')).forEach(i=>i.addEventListener('input',preview));for(const id of ['customer','project','quote_no','quote_date','mode','discount','depositPercent'])$(id).addEventListener('input',run(()=>{changed();preview();}));$('unit').onchange=()=>{const old=factors[S.unit],f=factors[val('unit')];for(const id of ['length','height','depth'])if(val(id)!=='')set(id,+(num(id)*old/f).toFixed(6));S.unit=val('unit');preview();};$('search').oninput=render;$('selectAll').onchange=()=>{S.selected=$('selectAll').checked?new Set(S.q.items.map((_,i)=>i)):new Set();render();};$('copyBtn').onclick=run(()=>duplicate([...S.selected]));$('deleteBtn').onclick=run(()=>{assertEditable();if(!S.selected.size)return;undoPoint();S.q.items=S.q.items.filter((_,i)=>!S.selected.has(i));S.selected.clear();changed();});$('undoBtn').onclick=run(()=>{assertEditable();if(!S.undo.length)return;S.q.items=S.undo.pop();S.selected.clear();changed();resetEntry();});$('batchQtyBtn').onclick=run(()=>{assertEditable();if(!S.selected.size)return;const v=prompt('Quantity for selected items / 所选行数量','1');if(v===null)return;if(!Number.isInteger(+v)||+v<1)throw Error('Positive integer required / 请输入正整数');undoPoint();S.selected.forEach(i=>S.q.items[i].qty=+v);changed();});$('batchMatBtn').onclick=run(()=>{assertEditable();if(!S.selected.size)return;const chosen=[...S.selected];const cats=new Set(chosen.map(i=>S.q.items[i].cat));if(cats.size!==1)throw Error('Select items from one category / 请选择同一品类的明细');const c=S.boot.categories.find(c=>c.key===S.q.items[chosen[0]].cat);modal(bi('Change material','批量修改材料'),`<select id="batchMaterial">${c.materials.map(m=>option(m.key,m.label_en+' / '+m.label)).join('')}</select>`,[{text:bi('Apply','应用'),primary:true,action:()=>{undoPoint();chosen.forEach(i=>S.q.items[i].material=val('batchMaterial'));changed();$('modal').close();}}]);});$('themeBtn').onclick=()=>{document.body.classList.toggle('dark');localStorage.setItem('vouguer-next-v4-theme',document.body.classList.contains('dark')?'dark':'light');};document.addEventListener('keydown',run(async e=>{const ctrl=e.ctrlKey||e.metaKey,typing=/INPUT|TEXTAREA|SELECT/.test(e.target.tagName);if(e.altKey&&['l','h','d'].includes(e.key.toLowerCase())){e.preventDefault();$({l:'length',h:'height',d:'depth'}[e.key.toLowerCase()]).focus();return;}if(ctrl&&e.key.toLowerCase()==='s'){e.preventDefault();await save();toast('Saved / 已保存');}if(ctrl&&e.key.toLowerCase()==='e'){e.preventDefault();await exportsModal();}if(ctrl&&e.key==='Enter'){e.preventDefault();addItem();}if(ctrl&&e.key.toLowerCase()==='z'&&!typing){e.preventDefault();$('undoBtn').click();}if(ctrl&&e.key.toLowerCase()==='d'&&!typing){e.preventDefault();duplicate([...S.selected]);}if(e.key==='Delete'&&!typing&&!$('modal').open)$('deleteBtn').click();if(e.key==='Escape'&&!$('modal').open)resetEntry();}));document.addEventListener('paste',run(async e=>{const file=[...(e.clipboardData?.files||[])].find(f=>f.type.startsWith('image/'))||[...(e.clipboardData?.items||[])].find(i=>i.type.startsWith('image/'))?.getAsFile();if(file){if($('modal').open&&!$('drawingFile'))return;e.preventDefault();if(!$('modal').open)drawing();await drawingPasteHandler?.(file);return;}if($('modal').open)return;const text=e.clipboardData?.getData('text')||'';const match=text.trim().match(/^(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*(mm|cm|ft|inch)?$/i);if(match){e.preventDefault();if(match[4]){set('unit',match[4].toLowerCase());S.unit=val('unit');}['length','height','depth'].forEach((id,i)=>set(id,match[i+1]));preview();toast('3D dimensions pasted / 已粘贴长高深');}}));window.addEventListener('beforeunload',e=>{if(S.rev>S.saved){e.preventDefault();e.returnValue='';}});}
async function boot(){if(localStorage.getItem('vouguer-next-v4-theme')==='dark')document.body.classList.add('dark');const [bootstrap,rawConfig]=await Promise.all([api('/api/bootstrap'),api('/api/config')]);bootstrap.ui_order=rawConfig.config.ui_order||{};S.order=bootstrap.ui_order;refreshBoot(bootstrap);bind();const id=localStorage.getItem('vouguer-next-v4-quote');if(id){try{adopt(await api('/api/quotes/'+id));}catch{adopt(await api('/api/quotes','POST',{quote_date:localDate()}));}}else adopt(await api('/api/quotes','POST',{quote_date:localDate()}));await syncContactDatalists(); }
run(boot)();
