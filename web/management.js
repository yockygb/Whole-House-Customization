'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>v==null?'待补成本 / Missing':'RM '+Number(v).toLocaleString('en-MY',{minimumFractionDigits:2,maximumFractionDigits:2});
const unitLabel=u=>u==='ft'?'FT':u;
const rateMoney=v=>v==null?money(v):'RM '+Number(v).toLocaleString('en-MY',{minimumFractionDigits:2,maximumFractionDigits:8});
const M={tab:'categories',config:null,materials:[],rates:[],categories:[],orders:{},catalogueDirty:false,pendingRefresh:false,orderSaving:false,editorSubmitting:false};
const tabs=[['categories','品类与材料关联','Categories & bindings'],['body','普通柜体材料库','General carcass materials'],['kitchen_body','厨房柜体材料库','Kitchen carcass materials'],['door','通用柜门材料库','Shared door materials'],['rates','品类关联价格','Category-specific rates'],['extras','增项管理','Add-ons'],['rules','高度 · 深度 · 非标','Dimension rules'],['costs','安装 · 运输 · 售后','Project costs'],['company','公司与导出设置','Company & exports'],['contacts','客户与项目','Customers & projects'],['backup','备份与恢复','Backup & restore']];
async function api(path,method='GET',data){const r=await fetch(path,{method,headers:data?{'Content-Type':'application/json'}:undefined,body:data?JSON.stringify(data):undefined});let j;try{j=await r.json();}catch{throw Error('后台返回了网页而非JSON（HTTP '+r.status+'），请完全退出并重新启动报价系统 / The server returned a web page instead of JSON; restart the quotation app');}if(!r.ok)throw Error(j.error||j.detail||'操作失败');return j;}
function notify(t,error=false){$('notice').textContent=t;$('notice').style.display='block';$('notice').style.background=error?'#923b3b':'#263b4e';clearTimeout(notify.timer);notify.timer=setTimeout(()=>$('notice').style.display='none',5000);}
const run=fn=>async(...args)=>{try{return await fn(...args);}catch(e){notify(e.message,true);console.error(e);}};
const option=(v,t,selected=false)=>`<option value="${esc(v)}" ${selected?'selected':''}>${esc(t)}</option>`;
function input(name,label,value='',type='text',hint=''){return `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${type==='number'?'min="0" step="any"':''}>${hint?`<small>${hint}</small>`:''}</label>`;}
function check(name,label,value=true){return `<label class="check"><input name="${name}" type="checkbox" ${value?'checked':''}>${label}</label>`;}
function table(heads,rows,sort){const sortable=Boolean(sort?.key),count=heads.length+(sortable?1:0),header=(sortable?'<th>排序 / Order</th>':'')+heads.map(h=>`<th>${h}</th>`).join(''),body=rows.length?rows.map(row=>{const id=sortable?row[0]:null,cells=sortable?row.slice(1):row;return `<tr${sortable?` data-order-row="${esc(id)}"`:''}>${sortable?`<td class="order-cell"><button type="button" class="sort-handle" data-order-handle="${esc(id)}" draggable="${sort.enabled!==false}" ${sort.enabled===false?'disabled':''} aria-label="拖动或用方向键排序 / Drag or use arrow keys to reorder" title="${sort.enabled===false?'清除筛选后可排序 / Clear filters to reorder':'拖动排序 / Drag to reorder'}">⠿</button></td>`:''}${cells.map(c=>`<td>${c}</td>`).join('')}</tr>`;}).join(''):`<tr><td colspan="${count}" class="empty">暂无记录，点击新增开始 / No records yet</td></tr>`;return `<div class="table-scroll"><table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div>`;}
function ordered(rows,key,id=row=>row.id){const ranks=new Map((M.orders[key]||[]).map((value,index)=>[value,index]));return rows.map((row,index)=>({row,index})).sort((a,b)=>(ranks.get(id(a.row))??Infinity)-(ranks.get(id(b.row))??Infinity)||a.index-b.index).map(entry=>entry.row);}
function ratePartOf(rate){return (M.materials||[]).find(m=>m.id===rate?.material_id)?.part||'';}
function categoryBodyPart(category){return category?.pricing_model==='kitchen_split'?'kitchen_body':'body';}
function rateSkeleton(category,rates){
 // Mirror of catalogue.effective_rate_order(): the saved list keeps its cross-part slots.
 const saved=(M.rate_orders||{})[category];
 if(Array.isArray(saved)&&saved.length){
  const known=new Set(rates.map(r=>r.id)),kept=saved.filter(id=>known.has(id));
  return [...kept,...rates.map(r=>r.id).filter(id=>!kept.includes(id))];
 }
 const categoryRow=(M.categories||[]).find(c=>c.key===category),body=categoryBodyPart(categoryRow);
 return [...rates.filter(r=>ratePartOf(r)===body).map(r=>r.id),
         ...rates.filter(r=>ratePartOf(r)!==body).map(r=>r.id)];
}
function mergePartOrder(ids,rates,part){
 // Reorder only one part's slots, so the other part and any hidden rows keep their place.
 const byId=new Map(rates.map(r=>[r.id,r]));
 const slots=ids.map((id,index)=>[id,index]).filter(([id])=>ratePartOf(byId.get(id))===part).map(([,index])=>index);
 if(!slots.length)return ids;
 const rank=new Map((M.orders['materials:'+part]||[]).map((mid,index)=>[mid,index]));
 const subset=slots.map(index=>ids[index]);
 const sorted=subset.map((id,index)=>({id,index}))
  .sort((a,b)=>((rank.get(byId.get(a.id)?.material_id)??Infinity)-(rank.get(byId.get(b.id)?.material_id)??Infinity))||a.index-b.index)
  .map(entry=>entry.id);
 const next=ids.slice();
 slots.forEach((slot,index)=>{next[slot]=sorted[index];});
 return next;
}
function effectiveRates(category,rows){
 // Derived server-side with the same precedence, so this table shows the order Quick
 // entry really uses (a newer library sort included).
 const order=(M.rate_orders||{})[category];
 if(!Array.isArray(order)||!order.length)return ordered(rows,'rates:'+category);
 const byId=new Map(rows.map(r=>[r.id,r])),rank=new Map(order.map((id,index)=>[id,index]));
 const listed=order.map(id=>byId.get(id)).filter(Boolean);
 return [...listed,...rows.filter(r=>!rank.has(r.id))];   // 派生列表外的记录保留在末尾
}
function applyAcceptedOrder(key,ids){
 // Only the derived rate lists are touched, so M.config and unsaved drafts stay intact.
 if(key.startsWith('rates:')){
  const category=key.slice('rates:'.length);
  if(!category)return;
  // The accepted list is now the newest saved rate order, so it *is* the derived
  // order (server keeps its cross-part slots and reorders nothing within a part).
  M.rate_orders={...(M.rate_orders||{}),[category]:ids.slice()};
  return;
 }
 if(!key.startsWith('materials:'))return;
 // A library sort is now the newest change for this part: every category showing that
 // part adopts the new order immediately, including the rates table in this session.
 const part=key.slice('materials:'.length);
 const categories=(M.categories||[]).filter(c=>part==='door'||categoryBodyPart(c)===part);
 const next={...(M.rate_orders||{})};
 for(const category of categories){
  const rates=(M.rates||[]).filter(r=>r.category_key===category.key);
  if(!rates.some(r=>ratePartOf(r)===part))continue;
  next[category.key]=mergePartOrder(rateSkeleton(category.key,rates),rates,part);
 }
 M.rate_orders=next;
}
function bindTableOrder(key,enabled,onOrder){const body=$('content').querySelector('table tbody');if(!body)return;const ids=()=>[...body.querySelectorAll('[data-order-row]')].map(row=>row.dataset.orderRow);const ready=()=>enabled&&!M.orderSaving;body.ondragover=e=>{if(ready()&&e.target.closest('[data-order-row]'))e.preventDefault();};body.ondrop=e=>{if(!ready())return;const target=e.target.closest('[data-order-row]'),from=e.dataTransfer?.getData('text/plain');if(!target||!from)return;e.preventDefault();const current=ids(),to=target.dataset.orderRow;if(from===to)return;const rect=target.getBoundingClientRect(),after=e.clientY>rect.top+rect.height/2;current.splice(current.indexOf(from),1);current.splice(current.indexOf(to)+(after?1:0),0,from);onOrder(current,from);};body.querySelectorAll('[data-order-handle]').forEach(handle=>{handle.ondragstart=e=>{if(!ready()){e.preventDefault();return;}e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',handle.dataset.orderHandle);};handle.onkeydown=e=>{const dir=e.key==='ArrowUp'?-1:e.key==='ArrowDown'?1:0;if(!dir||!ready())return;e.preventDefault();const current=ids(),from=current.indexOf(handle.dataset.orderHandle),to=from+dir;if(to<0||to>=current.length)return;current.splice(to,0,current.splice(from,1)[0]);onOrder(current,handle.dataset.orderHandle);};});}
// One persisted catalogue order is shared with Quick entry; keep both windows in step.
const CATALOGUE_CHANNEL='vouguer-catalogue-order';
function isDataField(target){const tag=(target?.tagName||'').toUpperCase();return (tag==='INPUT'||tag==='SELECT'||tag==='TEXTAREA')&&Boolean(target.getAttribute&&target.getAttribute('name'));}
function markDirty(){M.catalogueDirty=true;}
function refreshFromCatalogue(){
 if($('editor')?.open||M.catalogueDirty||M.orderSaving){
  if(!M.pendingRefresh)notify('Order changed in Quick entry; refresh is waiting for your unsaved edits / 排序已更新，待保存当前修改后刷新');
  M.pendingRefresh=true;
  return;
 }
 // Background refresh: reload rechecks the draft state after its GETs (see reload).
 run(()=>reload(true))();
}
function flushPendingRefresh(){
 if(!M.pendingRefresh)return;
 if($('editor')?.open||M.catalogueDirty||M.orderSaving)return;
 M.pendingRefresh=false;
 run(()=>reload(true))();
}
function afterSave(){
 // A successful explicit save persists the draft, so it is no longer unsaved and any
 // order refresh that was deferred meanwhile may now run.
 M.catalogueDirty=false;
 flushPendingRefresh();
}
function orderBus(){if(M.orderBus!==undefined)return M.orderBus;try{M.orderBus=typeof BroadcastChannel==='undefined'?null:new BroadcastChannel(CATALOGUE_CHANNEL);}catch(e){M.orderBus=null;}if(M.orderBus)M.orderBus.onmessage=()=>refreshFromCatalogue();return M.orderBus;}
function announceOrder(key){const bus=orderBus();if(bus)try{bus.postMessage({key});}catch(e){console.error(e);}}
function watchCatalogueOrder(){
 orderBus();
 // Every real editable field carries a name attribute (company, project costs,
 // dimension rules and the editor form all do). Filter/search boxes do not, so
 // they never block a refresh. Both input and change are tracked: selects and
 // checkboxes can fire only change.
 for(const root of [$('content'),$('editorBody')]){
  if(!root||!root.addEventListener)continue;
  for(const type of ['input','change'])root.addEventListener(type,e=>{if(isDataField(e.target))markDirty();});
 }
 const dialog=$('editor');
 if(dialog&&dialog.addEventListener)dialog.addEventListener('close',()=>{
  if(M.editorSubmitting)return;
  M.catalogueDirty=false;
  flushPendingRefresh();
 });
 if(typeof window==='undefined')return;
 let last=0;
 const refresh=()=>{const now=Date.now();if(now-last<1500)return;last=now;refreshFromCatalogue();};
 window.addEventListener('focus',refresh);
 document.addEventListener?.('visibilitychange',()=>{if(!document.hidden)refresh();});
}
async function persistOrder(key,ids,draw,focusId){
 if(M.orderSaving)return;                       // 串行保存：保存期间不再接受排序操作
 M.orderSaving=true;
 document.querySelectorAll('[data-order-handle]').forEach(b=>{b.disabled=true;});
 try{
  await api('/api/catalogue/order','POST',{key,ids});
  M.orders={...M.orders,[key]:ids};
  applyAcceptedOrder(key,ids);
  draw();
  M.catalogueDirty=false;
 }finally{
  M.orderSaving=false;
 }
 [...document.querySelectorAll('[data-order-handle]')].find(b=>b.dataset.orderHandle===focusId)?.focus();
 notify('排序已保存 / Order saved');
 announceOrder(key);
 flushPendingRefresh();
}
function editor(title,body,onSave,deleteMode=false){$('editorTitle').textContent=title;$('editorBody').innerHTML=body;$('editorError').textContent='';const action=$('editorForm').querySelector('button[type=submit]');action.textContent=deleteMode?'确认删除 / Delete':'保存 / Save';action.className=deleteMode?'danger':'primary';$('editorForm').onsubmit=async e=>{e.preventDefault();$('editorError').textContent='';const submit=e.submitter;submit.disabled=true;M.editorSubmitting=true;try{await onSave(new FormData(e.target));$('editor').close();await reload();announceOrder('catalogue');notify(deleteMode?'记录已删除；历史报价保留 / Item deleted; saved quotations preserved':'已保存，数据重启后保留 / Saved');}catch(err){$('editorError').textContent=err.message;}finally{M.editorSubmitting=false;submit.disabled=false;}};$('editor').showModal();}
const value=(f,k)=>String(f.get(k)??'').trim();
const nullable=(f,k)=>value(f,k)===''?null:Number(value(f,k));
async function reload(deferIfDirty=false){
 const [raw,catalog]=await Promise.all([api('/api/config'),api('/api/catalogue')]);
 // A background refresh must never draw over a draft the user started while these
 // GETs were in flight: recheck after the await and keep the refresh queued instead.
 if(deferIfDirty&&($('editor')?.open||M.catalogueDirty||M.orderSaving)){
  M.pendingRefresh=true;
  return;
 }
 M.config=raw.config;Object.assign(M,catalog);$('connection').textContent='Local · RM · V1.1 / 品类与报价体系';draw();M.catalogueDirty=false;M.pendingRefresh=false;
}
async function saveConfig(){await api('/api/config','PUT',{config:M.config});}
function draw(){const tab=tabs.find(t=>t[0]===M.tab);$('pageTitle').textContent=tab[1];$('sectionLabel').textContent=tab[2];$('navigation').innerHTML=tabs.map(([key,cn,en])=>`<button data-nav="${key}" class="${M.tab===key?'active':''}">${cn}<small>${en}</small></button>`).join('');document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>{M.tab=b.dataset.nav;M.catalogueDirty=false;draw();});({categories:categoriesPage,body:materialsPage,kitchen_body:materialsPage,door:materialsPage,rates:ratesPage,extras:extrasPage,rules:rulesPage,costs:costsPage,company:companyPage,contacts:contactsPage,backup:backupPage}[M.tab])();}

function categoriesPage(){
 const model={projection_split:'投影：柜体＋柜门 / ft²',kitchen_split:'橱柜：柜体 RM/FT＋柜门投影 RM/ft²',single_area:'单材料面积 / ft²'};
 const rows=ordered(M.categories,'categories',c=>c.key);
 $('content').innerHTML=`<div class="hint">先建立材料，再在品类中关联。一个品类可以关联多种柜体和柜门；同一材料可以被多个品类复用。普通柜体与厨房柜体分库维护；柜门材料及零售、成本价统一共用。</div><section class="panel"><div class="toolbar"><div><h2>品类与可用材料</h2><p>品类选择计价模型及柜体材料；柜门自动引用通用材料库。</p></div><button id="newCategory" class="primary">新增品类与关联材料</button></div>${table(['品类 / Category','计价模型 / Model','已关联柜体材料','已关联柜门','状态','操作'],rows.map(c=>{const links=M.rates.filter(r=>r.category_key===c.key&&r.enabled);const names=part=>links.filter(r=>M.materials.find(m=>m.id===r.material_id)?.part===part).map(r=>esc(M.materials.find(m=>m.id===r.material_id)?.name||'')).join('、');return [c.key,esc(c.name)+`<small>${esc(c.name_en)}</small>`,model[c.pricing_model]||esc(c.measure),names(c.pricing_model==='kitchen_split'?'kitchen_body':'body')||'未关联',names('door')||'无门 / 不适用',c.enabled===false?'已停用':'启用',`<button data-category="${esc(c.key)}">编辑品类与材料关联</button> <button class="danger" data-delete-category="${esc(c.key)}">删除 / Delete</button>`];}),{key:'categories'})}</section>`;
 $('newCategory').onclick=()=>categoryEditor();document.querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>categoryEditor(M.categories.find(c=>c.key===b.dataset.category)));document.querySelectorAll('[data-delete-category]').forEach(b=>b.onclick=run(()=>deleteCategory(M.categories.find(c=>c.key===b.dataset.deleteCategory))));bindTableOrder('categories',true,(ids,focus)=>persistOrder('categories',ids,categoriesPage,focus).catch(e=>notify(e.message,true)));
}
function deleteCategory(c){editor('删除品类 / Delete category',`<p>确认删除 <strong>${esc(c.name)}</strong>？</p><p>品类将从管理列表及新报价选项中移除；已有报价保留原品类和价格快照。</p><p>Remove this category from management and new quotations. Saved quotations keep their original category and price snapshots.</p>`,async()=>{await api('/api/catalogue/categories/'+encodeURIComponent(c.key),'DELETE');},true);}
function categoryEditor(existing){
 const c=existing||{name:'',name_en:'',pricing_model:'projection_split',enabled:true,std_depth_mm:600,default_height_mm:2400,min_height_ft:0,std_height_ft:0,cost_projection:true,nonstd_factor:1.2,height_tol_ft:.1,depth_tolerance_mm:10};
 editor(existing?'编辑品类与关联材料':'新增品类与关联材料',`<div class="form-grid">${input('name','品类名称 / Category',c.name)}${input('name_en','英文名称（可选）',c.name_en)}<label>计价模型 / Pricing model<select name="pricing_model" id="categoryModel">${[['projection_split','普通柜：投影柜体＋柜门'],['kitchen_split','橱柜：柜体按英尺(FT)＋柜门按投影'],['single_area','护墙等：单材料面积']].map(([v,t])=>option(v,t,c.pricing_model===v)).join('')}</select></label>${check('enabled','启用品类 / Enabled',c.enabled!==false)}</div><div id="categoryBindings"></div>`,async f=>{
  const bindings=[...$('editorBody').querySelectorAll('[data-link]:checked')].map(x=>({material_id:x.dataset.link,retail_price:Number($('retail_'+x.dataset.link).value),cost_price:$('cost_'+x.dataset.link).value===''?null:Number($('cost_'+x.dataset.link).value)}));
  await api('/api/catalogue/category','POST',{category:{...c,name:value(f,'name'),name_en:value(f,'name_en'),pricing_model:value(f,'pricing_model'),enabled:f.has('enabled')},bindings});
 });
 const render=()=>{const model=$('categoryModel').value;const roles=[model==='kitchen_split'?'kitchen_body':'body'];$('categoryBindings').innerHTML='<p class="hint">勾选柜体材料及其关联价格，普通柜关联普通柜体材料库，橱柜关联厨房柜体材料库，不内置固定板材。柜门由通用柜门库统一维护，普通柜及橱柜自动共用；开放柜报价可选择无门。</p>'+roles.map(part=>{const title={body:'普通柜体材料关联',kitchen_body:'厨房柜体材料关联',door:'柜门材料关联'}[part];const mats=M.materials.filter(m=>m.part===part&&m.enabled);return `<h3 class="binding-section">${title}</h3><input data-binding-search="${part}" placeholder="搜索此材料库的名称、品类或规格" aria-label="搜索${title}"><div class="table-scroll" data-binding-table="${part}"><table class="binding-table"><thead><tr><th>关联</th><th>材料 / 规格</th><th>本品类零售价 RM/${model==='kitchen_split'&&part==='kitchen_body'?'FT':'ft²'}</th><th>本品类成本价（可留空待补）</th></tr></thead><tbody>${mats.length?mats.map(m=>{const r=M.rates.find(r=>r.category_key===c.key&&r.material_id===m.id);return `<tr><td><input type="checkbox" data-link="${m.id}" ${r?.enabled?'checked':''} aria-label="关联${esc(m.name)}"></td><td>${esc(m.name)}<small>${esc(m.family)} · ${esc(m.spec)}</small></td><td><input id="retail_${m.id}" type="number" min="0" step="any" value="${r?.retail_price??0}" aria-label="${esc(m.name)}零售价"></td><td><input id="cost_${m.id}" type="number" min="0" step="any" value="${r?.cost_price??''}" aria-label="${esc(m.name)}成本价"></td></tr>`;}).join(''):'<tr><td colspan="4">该材料库暂无启用材料，请先新增材料。</td></tr>'}</tbody></table></div>`;}).join('');document.querySelectorAll('[data-binding-search]').forEach(input=>input.oninput=()=>{const rows=document.querySelector('[data-binding-table="'+input.dataset.bindingSearch+'"]').querySelectorAll('tbody tr');rows.forEach(row=>row.hidden=!row.textContent.toLowerCase().includes(input.value.toLowerCase()));});};$('categoryModel').onchange=render;render();
}

const materialTitles={body:'普通柜体材料',kitchen_body:'厨房柜体材料',door:'通用柜门材料'};
function materialCategories(part){return M.categories.filter(c=>(c.pricing_model==='kitchen_split')===(part==='kitchen_body'));}
function deleteMaterial(m){
 editor('删除材料 / Delete material',`<p>确认删除 <strong>${esc(m.name)}</strong>？</p><p>材料将从材料库及新报价选项中移除，历史报价保留原材料和金额。</p><p>Remove this material from the library and new quotations. Saved quotations keep their original materials and prices.</p>`,async()=>{await api('/api/catalogue/materials/'+encodeURIComponent(m.id),'DELETE');},true);
}

function materialsPage(){
 const part=M.tab,title=materialTitles[part],cats=materialCategories(part);
 const orderKey='materials:'+part;
 const description=part==='door'?'普通柜、地柜和吊柜共用本材料库及同一套柜门零售价、成本价。':part==='kitchen_body'?'地柜材料、吊柜材料按英尺(FT)分别维护零售价与成本价；柜门另用通用柜门库。':'普通定制柜按投影面积维护材料价格，不包含厨房地柜、吊柜的FT单价。';
 $('content').innerHTML=`<section class="panel"><div class="toolbar"><div><h2>${title}库</h2><p>${description}</p></div><button id="newMaterial" class="primary">新增${title}</button></div><div class="filter-row"><input id="materialSearch" placeholder="搜索品类、材料、系列或规格" aria-label="搜索材料"><select id="materialFamily" aria-label="筛选材料品类"><option value="">全部材料品类</option>${[...new Set(M.materials.filter(m=>m.part===part).map(m=>m.family))].map(f=>option(f,f)).join('')}</select>${part==='kitchen_body'?`<select id="materialUsage" aria-label="厨房柜体用途">${option('','地柜与吊柜材料 / All kitchen types')}${cats.map(c=>option(c.key,c.name+'材料')).join('')}</select>`:''}</div><div id="materialRows"></div></section>`;
 const render=()=>{const q=$('materialSearch').value.toLowerCase(),family=$('materialFamily').value,usage=$('materialUsage')?.value;const rows=ordered(M.materials.filter(m=>m.part===part&&(!family||m.family===family)&&JSON.stringify(m).toLowerCase().includes(q)&&(!usage||M.rates.some(r=>r.material_id===m.id&&r.category_key===usage&&r.enabled))),orderKey);const canSort=!q&&!family&&!usage;const links=m=>M.rates.filter(r=>r.material_id===m.id&&r.enabled&&cats.some(c=>c.key===r.category_key));const prices=(m,key)=>links(m).map(r=>esc(M.categories.find(c=>c.key===r.category_key)?.name)+'：'+rateMoney(r[key])+' / '+esc(unitLabel(r.unit))).join('<br>');$('materialRows').innerHTML=table(['材料品类','材料名称 / Name','规格 / Spec','适用范围与零售价','成本价','状态','操作'],rows.map(m=>[m.id,esc(m.family),esc(m.name)+`<small>${esc(m.name_en)}</small>`,esc(m.spec),(part==='door'?money(m.retail_price)+' / ft² · 普通柜与橱柜共用':prices(m,'retail_price'))||'<span class="muted">尚未关联品类</span>',part==='door'?money(m.cost_price)+' / ft²':prices(m,'cost_price')||'待设置',m.enabled?'启用':'已停用',`<button data-material="${m.id}">编辑材料 / 价格 / 适用范围</button> <button class="danger" data-delete-material="${m.id}">删除 / Delete</button>`]),{key:orderKey,enabled:canSort});document.querySelectorAll('[data-material]').forEach(b=>b.onclick=()=>materialEditor(part,M.materials.find(m=>m.id===b.dataset.material)));document.querySelectorAll('[data-delete-material]').forEach(b=>b.onclick=run(()=>deleteMaterial(M.materials.find(m=>m.id===b.dataset.deleteMaterial))));bindTableOrder(orderKey,canSort,(ids,focus)=>persistOrder(orderKey,ids,render,focus).catch(e=>notify(e.message,true)));};$('materialSearch').oninput=render;$('materialFamily').onchange=render;if($('materialUsage'))$('materialUsage').onchange=render;$('newMaterial').onclick=()=>materialEditor(part);render();
}

function materialEditor(part,existing){
 const m=existing||{part,family:'',name:'',name_en:'',spec:'',enabled:true};
 const pricing=part==='door'?`<h3>通用柜门价格 / Shared door prices</h3><div class="form-grid">${input('retail_price','零售价 RM/ft²',m.retail_price??'','number')}${input('cost_price','成本价 RM/ft²（可留空待补）',m.cost_price??'','number')}</div><p class="hint">普通柜、地柜和吊柜自动共用本门型及价格。修改影响新报价；历史报价保留原价格快照。</p>`:
 `<h3>适用范围与材料价格 / Material usage & rates</h3><div class="table-scroll"><table><thead><tr><th>启用关联</th><th>用途 / 单位</th><th>零售价 RM</th><th>成本价 RM（可留空）</th></tr></thead><tbody>${materialCategories(part).map(c=>{const r=M.rates.find(r=>r.material_id===m.id&&r.category_key===c.key);const unit=c.pricing_model==='kitchen_split'?'FT':'ft²';return `<tr><td><input type="checkbox" name="rate_categories" value="${esc(c.key)}" ${r?.enabled?'checked':''} aria-label="适用${esc(c.name)}"></td><td>${esc(c.name)} / ${unit}</td><td><input name="rate_price_${esc(c.key)}" type="number" min="0" step="any" value="${r?.retail_price??''}" aria-label="${esc(c.name)}材料零售价"></td><td><input name="rate_cost_${esc(c.key)}" type="number" min="0" step="any" value="${r?.cost_price??''}" aria-label="${esc(c.name)}材料成本价"></td></tr>`;}).join('')}</tbody></table></div><p class="hint">普通柜体和厨房柜体独立管理；地柜与吊柜分别维护每英尺(FT)价格。取消关联即可从该用途的新报价中移除。</p>`;
 editor((existing?'编辑':'新增')+materialTitles[part]+'、价格与适用范围',`<div class="form-grid">${input('family','材料品类（可直接新建名称）',m.family,'text','例如：多层板、颗粒板、PET门板、烤漆门')}${input('name','材料或系列名称 / Material name',m.name)}${input('name_en','英文名称（可选）',m.name_en)}${input('spec','规格 / Specification',m.spec)}${check('enabled','启用材料；停用不影响已保存报价',Boolean(m.enabled))}</div>${pricing}`,async f=>{
  const data={...m,part,family:value(f,'family'),name:value(f,'name'),name_en:value(f,'name_en'),spec:value(f,'spec'),enabled:f.has('enabled')};
  if(part==='door'){
   if(value(f,'retail_price')==='')throw Error('请填写通用柜门零售价');
   data.retail_price=Number(value(f,'retail_price'));data.cost_price=nullable(f,'cost_price');
  }else data.rates=f.getAll('rate_categories').map(key=>{if(value(f,'rate_price_'+key)==='')throw Error('请填写已勾选用途的材料零售价');return {category_key:key,retail_price:Number(value(f,'rate_price_'+key)),cost_price:nullable(f,'rate_cost_'+key)};});
  await api('/api/catalogue/materials','POST',data);
 });
}

function ratesPage(){
 $('content').innerHTML=`<section class="panel"><div class="toolbar"><div><h2>品类关联价格</h2><p>普通柜体、厨房柜体分库维护，柜门全品类共用同一价格。橱柜柜体 RM/FT 与柜门 RM/ft² 分开计价。</p></div><button id="editCategoryRates" class="primary">编辑当前品类的关联与价格</button></div><select id="rateCategory" aria-label="价格所属品类">${M.categories.map(c=>option(c.key,c.name)).join('')}</select><div id="rateRows"></div></section>`;
 const render=()=>{const cat=$('rateCategory').value,key='rates:'+cat,all=M.rates.filter(r=>r.category_key===cat&&r.enabled),rows=effectiveRates(cat,all);$('rateRows').innerHTML=table(['材料','材料用途','计价单位','零售价','成本价','关联状态','操作'],rows.map(r=>{const m=M.materials.find(m=>m.id===r.material_id);return [r.id,esc(m?.name),{body:'普通柜体',kitchen_body:'厨房柜体',door:'通用柜门'}[m?.part],esc(unitLabel(r.unit)),rateMoney(r.retail_price),rateMoney(r.cost_price),m?.enabled?'关联启用':'关联停用',`<button class="danger" data-delete-rate="${esc(r.id)}">删除 / Delete</button>`];}),{key});document.querySelectorAll('[data-delete-rate]').forEach(b=>b.onclick=run(()=>deleteRate(rows.find(r=>r.id===b.dataset.deleteRate))));bindTableOrder(key,true,(ids,focus)=>persistOrder(key,ids,render,focus).catch(e=>notify(e.message,true)));};$('rateCategory').onchange=render;$('editCategoryRates').onclick=()=>categoryEditor(M.categories.find(c=>c.key===$('rateCategory').value));render();
}
function deleteRate(r){const m=M.materials.find(m=>m.id===r.material_id),c=M.categories.find(c=>c.key===r.category_key);editor('删除品类价格关联 / Delete category rate',`<p>确认删除 <strong>${esc(c?.name)} — ${esc(m?.name)}</strong>？</p><p>此材料关联将从当前管理列表和新报价中移除；已保存报价不变。</p><p>Remove this material link from new quotations. Saved quotations are unchanged.</p>`,async()=>{await api('/api/catalogue/rates/'+encodeURIComponent(r.id),'DELETE');},true);}

function extrasPage(){
 const items=ordered(M.config.extras.items,'extras',e=>e.key);
 $('content').innerHTML=`<div class="hint">所有增项分别维护成本价与零售价。用量是本行总用量，不再乘柜子数量。玻璃升级填写的是差价，而不是完整门价。</div><section class="panel"><div class="toolbar"><h2>增项目录</h2><button id="newExtra" class="primary">新增增项</button></div>${table(['名称','计价依据 / 单位','零售价','成本价','适用品类','状态','操作'],items.map(e=>[e.key,esc(e.name)+`<small>${esc(e.name_en)}</small>`,{qty:'直接用量',length:'长度尺寸×数量',area:'宽×高×数量'}[e.basis||'qty']+' / '+esc(e.unit),money(e.price),money(e.cost_price),(e.cats||[]).map(k=>esc(M.categories.find(c=>c.key===k)?.name||k)).join('、'),e.needs_review?'需核对升级差价':e.enabled===false?'停用':'启用',`<button data-extra="${esc(e.key)}">编辑 / 启停</button> <button class="danger" data-delete-extra="${esc(e.key)}">删除 / Delete</button>`]),{key:'extras'})}</section>`;
 $('newExtra').onclick=()=>extraEditor();document.querySelectorAll('[data-extra]').forEach(b=>b.onclick=()=>extraEditor(items.find(e=>e.key===b.dataset.extra)));document.querySelectorAll('[data-delete-extra]').forEach(b=>b.onclick=run(()=>deleteExtra(items.find(e=>e.key===b.dataset.deleteExtra))));bindTableOrder('extras',true,(ids,focus)=>persistOrder('extras',ids,extrasPage,focus).catch(e=>notify(e.message,true)));
}
function deleteExtra(e){editor('删除增项 / Delete add-on',`<p>确认删除 <strong>${esc(e.name)}</strong>？</p><p>该项目将从管理列表和新报价中移除；已保存报价保留原增项及金额。</p><p>Remove this add-on from new quotations. Saved quotations keep their original item and amount.</p>`,async()=>{M.config.extras.items=M.config.extras.items.filter(item=>item.key!==e.key);await saveConfig();},true);}
function extraEditor(existing){const e=existing||{key:'extra_'+Date.now(),name:'',name_en:'',price:0,cost_price:null,unit:'pcs',basis:'qty',cats:[],enabled:true};editor(existing?'编辑增项':'新增增项',`<div class="form-grid">${input('name','增项名称',e.name)}${input('name_en','英文名称（可选）',e.name_en)}<label>计价依据<select name="basis" id="extraBasis">${[['qty','直接填写总用量'],['length','长度尺寸 × 件数'],['area','宽高尺寸 × 件数']].map(([v,t])=>option(v,t,e.basis===v)).join('')}</select></label><label>单价单位<select name="unit" id="extraUnit"></select></label>${input('price','零售价 RM',e.price,'number')}${input('cost_price','成本价 RM（留空表示待补）',e.cost_price??'','number')}<label>收费性质<select name="charge_kind">${option('addition','独立附加项目',e.charge_kind!=='upgrade')}${option('upgrade','已有基础门的升级差价',e.charge_kind==='upgrade')}</select></label>${check('enabled','启用增项',e.enabled!==false)}${check('auto_with_cabinet','橱柜自动按柜体长度×数量计入（仅长度增项）',Boolean(e.auto_with_cabinet))}<label class="span-all">说明<textarea name="note">${esc(e.note||'')}</textarea></label></div><h3>适用品类（至少选择一个）</h3><div class="form-grid">${M.categories.map(c=>`<label class="check"><input type="checkbox" name="cats" value="${esc(c.key)}" ${(e.cats||[]).includes(c.key)?'checked':''}>${esc(c.name)}</label>`).join('')}</div>`,async f=>{const cats=f.getAll('cats');if(!cats.length)throw Error('请至少选择一个适用品类');const next={...e,name:value(f,'name'),name_en:value(f,'name_en'),price:Number(value(f,'price')),cost_price:nullable(f,'cost_price'),basis:value(f,'basis'),unit:value(f,'unit'),charge_kind:value(f,'charge_kind'),enabled:f.has('enabled'),auto_with_cabinet:f.has('auto_with_cabinet'),cats,note:value(f,'note'),needs_review:false};if(!next.name)throw Error('请填写名称');const i=M.config.extras.items.findIndex(x=>x.key===e.key);if(i<0)M.config.extras.items.push(next);else M.config.extras.items[i]=next;await saveConfig();});const units=()=>{const basis=$('extraBasis').value;$('extraUnit').innerHTML=({qty:['pcs','set','m','ft','m2','ft2'],length:['m','ft'],area:['m2','ft2']}[basis]).map(u=>option(u,({pcs:'个 pcs',set:'套 set',m:'米 m',ft:'英尺 ft',m2:'平方米 m²',ft2:'平方英尺 ft²'})[u],e.unit.replace('²','2')===u)).join('');};$('extraBasis').onchange=units;units();}

function rulesPage(){
 $('content').innerHTML=`<section class="panel"><div class="toolbar"><div><h2>按品类维护尺寸与非标规则</h2><p>计费规则影响报价；内部安装与运输始终使用实际宽高投影。</p></div></div><select id="ruleCategory" aria-label="规则所属品类">${M.categories.map(c=>option(c.key,c.name)).join('')}</select><div id="ruleForm"></div></section>`;
 const render=()=>{const c=M.categories.find(c=>c.key===$('ruleCategory').value);$('ruleForm').innerHTML=`<form id="rulesSave"><div class="form-grid" style="margin-top:20px">${input('default_height_mm','默认高度 mm',c.default_height_mm||0,'number')}${input('std_depth_mm','标准深度 mm',c.std_depth_mm||0,'number')}${input('min_height_ft','最低计价高度 ft',c.min_height_ft||0,'number')}${input('std_height_mm','标准高度 mm',(c.std_height_ft||0)*(M.config.meta.mm_per_ft||304.8),'number')}${input('height_tol_ft','高度容差 ft',c.height_tol_ft??.1,'number')}${input('depth_tolerance_mm','橱柜深度容差 mm',c.depth_tolerance_mm??10,'number')}${input('nonstd_factor','橱柜非标系数（只乘一次）',c.nonstd_factor??1.2,'number')}${check('check_height','橱柜按标准高度检查非标',Boolean(c.check_height))}${check('ignore_depth','投影计价忽略深度系数',Boolean(c.ignore_depth))}${check('cost_projection','本品类参与安装及运输实际投影',c.cost_projection!==false)}</div><p class="hint">普通柜超深系数＝实际深度÷标准深度，浅于标准不降价。橱柜多项非标条件同时命中时只应用一次非标系数。规则不作用于独立增项。橱柜柜门的最低高度与超深规则沿用“定制柜”品类，柜体非标系数不套给柜门或脚线。</p><button class="primary">保存本品类规则</button></form>`;$('rulesSave').onsubmit=run(async ev=>{ev.preventDefault();const f=new FormData(ev.target);const target=M.config.categories.find(x=>x.key===c.key);for(const k of ['default_height_mm','std_depth_mm','min_height_ft','height_tol_ft','depth_tolerance_mm','nonstd_factor'])target[k]=Number(value(f,k));target.std_height_ft=Number(value(f,'std_height_mm'))/(M.config.meta.mm_per_ft||304.8);for(const k of ['check_height','ignore_depth','cost_projection'])target[k]=f.has(k);await saveConfig();await reload();notify('规则已保存；已保存报价仍保留原规则');});};$('ruleCategory').onchange=render;render();
}

function costsPage(){const p=M.config.project_costs;
 $('content').innerHTML=`<section class="panel"><div class="toolbar"><div><h2>项目成本默认参数</h2><p>仅影响新报价；已保存报价有自己的参数快照，单份报价也可独立调整。</p></div></div><form id="costSave"><div class="form-grid">${input('installation_per_m2','安装单价 RM/m²',p.installation_per_m2,'number')}${input('volume_per_m2','运输体积系数 m³/m²',p.volume_per_m2,'number','10m²＝1.62m³，即每平方米0.162m³')}${input('transport_per_m3','运输单价 RM/m³',p.transport_per_m3,'number')}${input('after_sales_percent','售后成本比例 %',p.after_sales_rate*100,'number','基数为折后未税成交额，定金不影响计算')}</div><div class="sample cost-formula">实际投影＝所有柜体实际宽×高×数量，柜体和门只统计一次。<br>安装费＝实际投影m²×安装单价。<br>运输费＝实际投影m²×体积系数×运输单价。<br>项目预计利润＝折后未税成交额－材料及增项成本－安装－运输－售后。</div><div class="form-actions"><button class="primary">保存新报价默认参数</button></div></form></section>`;
 $('costSave').onsubmit=run(async e=>{e.preventDefault();const f=new FormData(e.target);M.config.project_costs={installation_per_m2:Number(value(f,'installation_per_m2')),volume_per_m2:Number(value(f,'volume_per_m2')),transport_per_m3:Number(value(f,'transport_per_m3')),after_sales_rate:Number(value(f,'after_sales_percent'))/100};await saveConfig();await reload();notify('新报价成本默认参数已保存');});
}

function companyPage(){const c=M.config.company,t=M.config.totals||{};
 $('content').innerHTML=`<section class="panel"><h2>公司资料与导出设置</h2><form id="companySave"><div class="form-grid">${input('name','Company name / 公司英文名',c.name)}${input('name_cn','公司中文名',c.name_cn)}${input('address','Address / 英文地址',c.address)}${input('address_cn','中文地址',c.address_cn)}${input('phone','Phone / 电话',c.phone)}${input('email','Email / 邮箱',c.email)}${check('show_discount_row','客户报价显示折扣及折后金额',Boolean(t.show_discount_row))}${check('show_deposit_rows','客户报价显示定金及余款',Boolean(t.show_deposit_rows))}</div><div class="form-actions"><button class="primary">保存公司与导出设置</button></div></form><h3>公司 Logo</h3><input type="file" id="companyLogo" accept="image/png,image/jpeg" aria-label="上传公司标志"><p class="muted">客户版沿用当前报价版式。内部成本、利润及成本参数不会写入客户版。</p></section>`;
 $('companySave').onsubmit=run(async e=>{e.preventDefault();const f=new FormData(e.target);for(const k of ['name','name_cn','address','address_cn','phone','email'])M.config.company[k]=value(f,k);M.config.totals={...t,show_discount_row:f.has('show_discount_row'),show_deposit_rows:f.has('show_deposit_rows')};await saveConfig();afterSave();notify('公司资料及导出设置已保存');});$('companyLogo').onchange=run(async e=>{const file=e.target.files[0];if(!file)return;const data=await readData(file);await api('/api/logo','POST',{data});notify('Logo已保存');});
}
async function readData(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(file);});}
async function contactsPage(){const [customers,projects]=await Promise.all([api('/api/customers'),api('/api/projects')]);if(M.tab!=='contacts')return;$('content').innerHTML=['customers','projects'].map(type=>{const rows=type==='customers'?customers.customers:projects.projects;return `<section class="panel"><div class="toolbar"><h2>${type==='customers'?'客户':'项目'}</h2><button data-contact-new="${type}" class="primary">新增</button></div>${table(['名称','电话 / 地址','操作'],rows.map(r=>[esc(r.name),esc(r.phone||r.address||''),`<button data-contact="${type}" data-id="${r.id}">编辑</button>`]))}</section>`;}).join('');const editContact=(type,r={})=>editor(type==='customers'?'客户资料':'项目资料',`<div class="form-grid">${input('name','名称 / Name',r.name)}${input('phone','电话 / Phone',r.phone)}${input('address','地址 / Address',r.address)}</div>`,async f=>{if(!value(f,'name'))throw Error('请填写名称');await api('/api/'+type+(r.id?'/'+r.id:''),r.id?'PUT':'POST',{...r,name:value(f,'name'),phone:value(f,'phone'),address:value(f,'address')});});document.querySelectorAll('[data-contact-new]').forEach(b=>b.onclick=()=>editContact(b.dataset.contactNew));document.querySelectorAll('[data-contact]').forEach(b=>b.onclick=()=>editContact(b.dataset.contact,(b.dataset.contact==='customers'?customers.customers:projects.projects).find(r=>r.id===Number(b.dataset.id))));}
function backupPage(){$('content').innerHTML=`<section class="panel"><h2>完整业务备份</h2><p>包含客户、项目、报价、价格快照、共享材料库、品类关联价格及成本参数。</p><a href="/api/backup" download><button class="primary">下载完整备份</button></a></section><section class="panel"><h2>恢复备份</h2><p>恢复会替换当前系统数据，恢复前自动保存回退备份；不影响其他备份。</p><input id="restoreFile" type="file" accept=".json" aria-label="选择备份文件"><div class="form-actions"><button id="restoreBackup" class="danger">恢复所选备份</button></div></section>`;$('restoreBackup').onclick=run(async()=>{const file=$('restoreFile').files[0];if(!file)throw Error('请先选择备份文件');if(!confirm('将替换当前系统数据，确认恢复？'))return;await api('/api/restore','POST',JSON.parse(await file.text()));await reload();notify('恢复完成');});}
$('closeEditor').onclick=$('cancelEditor').onclick=()=>$('editor').close();
watchCatalogueOrder();
run(reload)();
