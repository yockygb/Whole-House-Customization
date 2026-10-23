'use strict';
async function loadQuoteCatalogue(){
 if(!S.q)return;
 const id=S.q.id,b=await api(`/api/quotes/${id}/catalogue`);
 if(S.q.id!==id)return;
 const selected=S.cat;refreshBoot(b);S.cat=b.categories.some(c=>c.key===selected)?selected:b.categories[0].key;
 selectCategory(S.cat,false);set('mode',S.q.mode);renderProjectCosts();
}
function renderProjectCosts(){
 const trigger=$('internalProjectBtn');if(trigger)trigger.onclick=openInternalProjectManagement;
 if($('modal').open&&$('projectCosts'))renderInternalProjectCosts();
}
function openInternalProjectManagement(){
 modal(bi('Internal project management','内部项目管理'),'<section id="projectCosts" class="project-cost-window"></section>');
 $('modal').dataset.internalProject='true';
 renderInternalProjectCosts();
}
function renderInternalProjectCosts(){
 const el=$('projectCosts');if(!el)return;
 const s=S.computed.summary||{};
 if(s.actual_projection_m2==null){el.innerHTML=`<h3>${bi('Historical calculation','历史报价口径')}</h3><p>Saved prices are preserved. Refresh prices explicitly to use the new cost model.<br>原价格及金额保留；手动更新价格后可使用新版成本核算。</p><button id="refreshPrices">${bi('Review latest prices','预览更新价格')}</button>`;}
 else{
 const items=[['Actual projection','实际投影',Number(s.actual_projection_m2).toFixed(3)+' m²'],['Estimated volume','估算运输体积',Number(s.estimated_volume_m3).toFixed(3)+' m³'],['Materials & add-ons','材料及增项成本',money(s.material_cost)],['Installation','总安装费',money(s.installation_cost)],['Transport','总运输费',money(s.transport_cost)],['After-sales reserve','售后预留',money(s.after_sales_cost)],['Total project cost','项目总成本',money(s.project_total_cost)],['Estimated profit','项目预计利润',s.cost_complete?money(s.estimated_profit):'Missing costs / 成本待补']];
 el.innerHTML=`<div class="project-cost-title"><h3>${bi('Internal project costs','内部项目成本')}</h3><div><button id="costBreakdown">${bi('Area & volume details','面积与体积明细')}</button><button id="quoteCostPolicy" ${S.q.locked?'disabled':''}>${bi('This quote’s rates','本单成本参数')}</button><button id="refreshPrices" ${S.q.locked?'disabled':''}>${bi('Review latest prices','预览更新价格')}</button></div></div><div class="cost-metrics">${items.map(([en,cn,value])=>`<div><small>${bi(en,cn)}</small><strong>${esc(value)}</strong></div>`).join('')}</div><p>Internal only · Actual area, not billable area · Add-on quantities are totals for this line.<br>仅内部核算；面积不套最低高度或深度系数；增项填写本行总用量。${s.cost_complete?'':' 部分增项或材料成本未填写，当前总成本不完整。'}</p>`;
 $('costBreakdown').onclick=()=>modal(bi('Projection & transport details','实际投影与运输明细'),table(['Cabinet / 柜体','Qty / 数量','Actual area m² / 实际投影','Estimated m³ / 估算体积'],S.computed.lines.map(l=>[esc(l.cab_name||l.cat_name),l.qty,Number(l.actual_projection_m2||0).toFixed(4),Number(l.estimated_volume_m3||0).toFixed(4)])));
 $('quoteCostPolicy').onclick=()=>{const p=s.cost_policy;modal(bi('This quotation only','仅修改本报价成本参数'),['installation_per_m2','volume_per_m2','transport_per_m3','after_sales_rate'].map((k,i)=>field('policy_'+k,['Installation RM/m²','Volume m³/m²','Transport RM/m³','After-sales rate (0–1)'][i],['安装单价','体积系数','运输单价','售后比例'][i],p[k],'number')).join(''),[{text:bi('Save this quotation','保存本单参数'),primary:true,action:async()=>{const p={};for(const k of Object.keys(s.cost_policy))p[k]=num('policy_'+k);adopt(await api(`/api/quotes/${S.q.id}/cost-policy`,'POST',p));$('modal').close();}}]);};
 }
 $('refreshPrices').onclick=run(async()=>{await save();const p=await api(`/api/quotes/${S.q.id}/refresh-prices`,'POST',{});if(!confirm(`Original / 原报价 ${money(p.before.net_total)}\nLatest / 最新报价 ${money(p.after.net_total)}\nApply current materials, rates and rules? Manual line prices remain unchanged.\n更新为当前材料、价格和规则？已手动填写的行单价保持不变。`))return;adopt(await api(`/api/quotes/${S.q.id}/refresh-prices`,'POST',{apply:true}));});
}
$('modal').addEventListener('close',()=>{
 if($('modal').dataset.internalProject==='true'){
  $('modalBody').innerHTML='';$('modalFooter').innerHTML='';
  $('modalTitle').textContent='';$('modalSubtitle').textContent='';
  delete $('modal').dataset.internalProject;
 }
});
