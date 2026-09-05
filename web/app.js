"use strict";
const pages=[['overview','市场总览','◫'],['holdings','持仓监控','▤'],['sectors','板块雷达','▦'],['candidates','尾盘候选','◷'],['timeline','信号时间线','≋'],['health','系统健康','⚙']];
const $=id=>document.getElementById(id);let state=null;let draft=null;let draftRevision=null;let saveBusy=false;
const escape=value=>String(value??'—').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const metric=(label,value,note)=>`<div class="metric"><span class="muted">${escape(label)}</span><strong>${escape(value)}</strong><small>${escape(note)}</small></div>`;
const panel=(title,body)=>`<section class="panel"><h3>${title}</h3>${body}</section>`;
const empty=(title,body)=>`<div class="empty"><div class="empty-symbol" aria-hidden="true">∅</div><h2>${title}</h2><p class="muted">${body}</p></div>`;
const table=(heads,rows)=>`<div class="table-wrap"><table><thead><tr>${heads.map(x=>`<th>${escape(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(x=>`<td>${escape(x)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
function render(){
 const id=location.hash.slice(1),page=pages.find(p=>p[0]===id)||pages[0];
 $('navigation').innerHTML=pages.map(p=>`<a class="nav-link" href="#${p[0]}" ${p===page?'aria-current="page"':''}><span aria-hidden="true">${p[2]}</span><span>${p[1]}</span></a>`).join('');$('title').textContent=page[1];document.title=`${page[1]} · StockReal`;
 if(!state)return;const s=state,b=s.manual_evidence.board;let html='';
 $('contract-count').textContent=`${s.contracts.passed} / ${s.contracts.total}`;
 if(page[0]==='overview')html=`<section class="panel hero"><span class="tag amber">风险评估 · 未启用</span><h2>先确认数据，再形成判断</h2><p class="muted">字段契约和交易日历尚未通过验收。当前保留诊断证据，不输出市场方向、持仓风险结论或交易提示。</p></section><div class="metrics">${metric('已配置持仓',s.holdings.holdings.length,'上限 20，只观察个人持仓')}${metric('本轮手动请求',s.manual_evidence.attempts,'非实时采集成功率')}${metric('板块样本覆盖',b.unique_codes??'—','本次分页的唯一代码数')}</div><div class="split">${panel('继续推进的条件','<div class="step"><span class="step-number">1</span><div><strong>字段和单位核对</strong><p>源时间、位置列、净额语义与空值行为。</p></div></div><div class="step"><span class="step-number">2</span><div><strong>交易日历人工确认</strong><p>当前及下一年度完整覆盖。自动采集维持关闭。</p></div></div>')}${panel('数据缺失如何处理','<p class="muted">批量板块广度尚无验证来源，广度与热度保持未评估。缺失值不会替换为零。</p><span class="tag">NOT_EVALUATED</span>')}</div>`;
 if(page[0]==='holdings')html=holdingsView(s);
 if(page[0]==='sectors')html=`<div class="metrics">${metric('观察到的板块',b.unique_codes??'—','仅代表本轮样本')}${metric('返回声明总数',b.declared_count??'—','同批次分页计数')}${metric('批量广度','未评估','没有已验证的 N_up / N_valid')}</div>`+panel('广度与热度降级',table(['指标','状态','原因'],[['Breadth','NOT_EVALUATED','批量上涨/有效家数未验证'],['SectorHeatScore','NOT_EVALUATED','广度缺源'],['DivergenceBaseScore','NOT_EVALUATED','广度缺源'],['DivergenceScore','NOT_EVALUATED','广度与成分股净流入缺源']]))+panel('分页证据','<p class="muted">本轮五页覆盖 270 个唯一板块，与返回总数一致；这不能证明交易时段排序稳定或原子截面。FIR / Rank 观察也等待字段契约通过。</p>');
 if(page[0]==='candidates')html=panel('尾盘候选',empty('候选流程尚未启用','当前没有运行尾盘采集。候选为空不表示市场没有候选。'))+panel('一期漏斗边界',table(['层级','状态'],[['批量候选来源','NOT_EVALUATED · 字段待验证'],['VWAP / 价差 / 可成交性','NOT_EVALUATED · 一期缺源'],['筹码层','NOT_EVALUATED · 一期不启用']]))+'<p class="subtle">启用后的候选仅为 INFO_CANDIDATE，14:56:30 到期；不增加候选 L2 请求。</p>';
 if(page[0]==='timeline')html=panel('信号时间线',empty('尚无生产信号','方向性输出未启用，当前不生成或推送信号。'))+panel('已有诊断审计',`<div class="metrics">${metric('离线回放批次',s.audit.runs,'同批次重复导入不会增加')}${metric('质量诊断条数',s.audit.events,'与生产信号分开记录')}</div><p class="muted">这里展示已保存的诊断统计。信号生成、阻断与通知的完整时间线仍待业务实现。</p>`);
 if(page[0]==='health')html=`<div class="metrics">${metric('本地已计调用',s.budget.used,'仅含已接入预算账本的请求')}${metric('普通额度余量',s.budget.normal_remaining,'本地 60,000 次控制预算')}${metric('预留已用',s.budget.reserve_used,'本地 20,000 次预留')}</div>`+panel('运行状态',table(['项目','状态'],[['自动采集','关闭 · 用户已确认'],['字段契约',`${s.contracts.passed} / ${s.contracts.total} 通过`],['交易日历',s.gate.calendar_status],['数据库',s.audit.journal_mode],['模式','只读诊断预览；不是生产上线']]))+panel('最近一次有限手动补测',table(['端点','HTTP','行数','耗时','质量标记'],s.manual_evidence.probes.map(p=>[p.endpoint_code,p.http_status,p.row_count,`${p.elapsed_ms} ms`,(p.quality_flags||[]).join(' / ')])))+'<p class="subtle">以上耗时只代表本轮手动样本，不代表盘中延迟或最近五个交易日成功率。预算是本地限制，不是供应商余额。</p>';
 $('view').innerHTML=html;if(page[0]==='holdings')bindHoldings();
}
async function refresh(){const button=$('refresh');button.disabled=true;$('view').classList.add('loading');try{const response=await fetch('/api/status',{cache:'no-store'});if(!response.ok)throw Error('unavailable');state=await response.json();$('updated').textContent='状态读取于 '+new Date(state.generated_at).toLocaleString('zh-CN',{hour12:false});render();}catch(error){state=null;$('contract-count').textContent='—';$('updated').textContent='状态读取失败';$('view').innerHTML=panel('暂时无法读取本机状态','<p class="muted">请检查服务器服务或 SSH 连接，然后点击刷新重试。未显示缓存状态，以免误认作最新状态。</p>');}finally{button.disabled=false;$('view').classList.remove('loading');}}
window.addEventListener('hashchange',render);$('refresh').addEventListener('click',refresh);render();refresh();

function holdingsView(s){
 if(draft!==null){
  const rows=draft.map((h,i)=>`<div class="holding-row"><label>股票代码<input data-row="${i}" data-field="symbol" aria-label="第 ${i+1} 行股票代码" value="${escape(h.symbol)}" placeholder="六位代码.SH / SZ / BJ" required pattern="[0-9]{6}[.](SH|SZ|BJ)" maxlength="9"></label><label>参考成本（可留空）<input data-row="${i}" data-field="reference_cost" aria-label="第 ${i+1} 行参考成本" value="${escape(h.reference_cost??'')}" inputmode="decimal" placeholder="未填写" pattern="[0-9]{1,12}([.][0-9]{1,4})?"></label><label>观察级别<input data-row="${i}" data-field="observation_level" aria-label="第 ${i+1} 行观察级别" value="${escape(h.observation_level)}" required maxlength="32"></label><button type="button" data-remove="${i}" aria-label="移除第 ${i+1} 行">移除</button></div>`).join('');
  return panel('编辑个人持仓',`<form id="holdings-form"><p class="muted">最多 20 只。观察级别是个人标签，不改变采集频率。只有保存后才会更新配置。</p><fieldset ${saveBusy?'disabled':''}>${rows||'<p class="muted">当前草稿为空，可以添加一行。</p>'}<div class="form-actions"><button type="button" id="add-holding" ${draft.length>=20?'disabled':''}>＋ 添加一行</button><button type="submit" class="primary">${saveBusy?'正在保存…':'保存持仓'}</button><button type="button" id="cancel-holdings">放弃草稿</button></div></fieldset><p id="save-message" role="status"></p></form>`);
 }
 return panel('个人持仓',`<div class="form-actions"><span class="tag">配置版本 ${escape(s.holdings.revision)}</span><button id="edit-holdings" class="primary">编辑持仓</button></div>`+(s.holdings.holdings.length?table(['代码','参考成本','观察级别'],s.holdings.holdings.map(h=>[h.symbol,h.reference_cost??'未填写',h.observation_level])):empty('尚未配置持仓','添加你希望观察的持仓；参考成本可以暂时留空。')))+panel('配置与行情分开处理','<p class="muted">保存只更新个人配置，自动采集继续关闭。代码目前进行格式校验，证券真实性待基础资料契约核对。盘口证据和风险判断尚未启用。</p>');
}
function bindHoldings(){
 if(draft===null){$('edit-holdings').addEventListener('click',()=>{draft=state.holdings.holdings.map(h=>({...h}));draftRevision=state.holdings.revision;render();});return;}
 document.querySelectorAll('[data-field]').forEach(input=>input.addEventListener('input',()=>{draft[Number(input.dataset.row)][input.dataset.field]=input.value;}));
 document.querySelectorAll('[data-remove]').forEach(button=>button.addEventListener('click',()=>{draft.splice(Number(button.dataset.remove),1);render();}));
 $('add-holding').addEventListener('click',()=>{draft.push({symbol:'',reference_cost:null,observation_level:'普通观察'});render();});
 $('cancel-holdings').addEventListener('click',()=>{draft=null;draftRevision=null;refresh();});
 $('holdings-form').addEventListener('submit',async event=>{
  event.preventDefault();if(saveBusy)return;saveBusy=true;render();
  try{
   const response=await fetch('/api/holdings',{method:'PUT',headers:{'Content-Type':'application/json','X-StockReal-Config':'1'},body:JSON.stringify({expected_revision:draftRevision,holdings:draft.map(h=>({...h,reference_cost:h.reference_cost===''?null:h.reference_cost}))})});
   if(!response.ok){const messages={409:'配置已在其他页面或终端更新。草稿已保留，请放弃草稿后重新读取，再合并你的修改。',400:'请检查代码是否重复、成本是否为正数，以及观察级别是否为空。'};throw Error(messages[response.status]||'暂时无法保存，请稍后重试。');}
   draft=null;draftRevision=null;await refresh();$('updated').textContent='持仓已保存 · 自动采集仍关闭';
  }catch(error){if($('save-message'))$('save-message').textContent=error.message;}
  finally{saveBusy=false;const fieldset=document.querySelector('#holdings-form fieldset');if(fieldset){fieldset.disabled=false;const submit=fieldset.querySelector('[type="submit"]');if(submit)submit.textContent='保存持仓';}}
 });
}
