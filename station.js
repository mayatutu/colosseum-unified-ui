/* Original UI extension; no replacement recording or review state machine. */
const stationPath=location.pathname.split('/').filter(Boolean);
const STATION_BASE=stationPath.length===2&&stationPath[0]==='s'?'/s/'+stationPath[1]:'';
const STATION_KEY=STATION_BASE||'local';
function stationURL(path){return STATION_BASE+path}
function readDraft(key){try{return JSON.parse(sessionStorage.getItem(key)||'null')}catch(e){return null}}
function writeDraft(key,value){try{sessionStorage.setItem(key,JSON.stringify(value))}catch(e){}}
function bindStationFormDraft(){
 const ids=['instruction',...(CFG.scene_persistence_enabled?[]:['scene']),'evaluator','maxsteps',...(CFG.feishu?.enabled?['feishuDevice']:[])],key='station-form:'+STATION_KEY,saved=readDraft(key);
 if(saved)for(const id of ids)if(saved[id]!==undefined)$('#'+id).value=saved[id];
 const save=()=>writeDraft(key,Object.fromEntries(ids.map(id=>[id,$('#'+id).value])));
 for(const id of ids){$('#'+id).addEventListener('input',save);$('#'+id).addEventListener('change',save)}
}
function clearReviewDraft(id){try{sessionStorage.removeItem('station-review:'+STATION_KEY+':'+id)}catch(e){}}
function bindReviewDraft(id,d){
 const key='station-review:'+STATION_KEY+':'+id;
 const baseline=JSON.stringify([d.feedback,d.preference,d.runs.map(r=>[r.side,r.score]),d.task_difficulty]);
 const saved=readDraft(key);
 if(saved?.baseline===baseline){
  $('#fb').value=saved.feedback;pref=saved.preference;
  if($('#taskDifficulty'))$('#taskDifficulty').value=saved.task_difficulty??'';
  for(const side of ['A','B'])if($('#sc-'+side)){$('#sc-'+side).value=saved['score_'+side];$('#rg-'+side).value=saved['score_'+side]||0}
  document.querySelectorAll('[data-pref]').forEach(b=>b.classList.toggle('on',b.dataset.pref===pref));
 }else if(saved)clearReviewDraft(id);
 const save=()=>writeDraft(key,{baseline,feedback:$('#fb').value,preference:pref,
  task_difficulty:$('#taskDifficulty')?.value??'',
  score_A:$('#sc-A')?.value||'',score_B:$('#sc-B')?.value||''});
 for(const el of document.querySelectorAll('#fb,#sc-A,#sc-B,#rg-A,#rg-B,#taskDifficulty'))el.addEventListener('input',save);
 for(const el of document.querySelectorAll('[data-pref]'))el.addEventListener('click',save);
}
window.addEventListener('message',e=>{
 if(e.origin!==location.origin||e.source!==parent||parent===window)return;
 if(e.data?.type==='hub-hidden')document.querySelectorAll('video').forEach(v=>v.pause());
 if(e.data?.type==='hub-language'&&['en','zh-CN'].includes(e.data.language))setLanguage(e.data.language);
});
async function allEvaluations() {
  const items=[];
  for(let offset=0;;) {
    const page=await api(`/api/evals?paginated=true&offset=${offset}&limit=5000`);
    items.push(...page.items);offset+=page.items.length;
    if(!page.items.length||offset>=page.total) return items;
  }
}
function setupSceneSaving(){
 if(!CFG.scene_persistence_enabled)return;
 const input=$('#scene'),row=document.createElement('div');row.className='row';row.style.marginTop='8px';
 const button=document.createElement('button');button.type='button';button.id='sceneSave';button.className='small';button.textContent=tr('Confirm and save scene');
 const status=document.createElement('span');status.id='sceneSaveStatus';status.setAttribute('role','status');status.className='mut';
 row.append(button,status);input.insertAdjacentElement('afterend',row);
 const update=()=>{const same=input.value.trim()===CFG.scene;button.disabled=same;status.textContent=tr(same?'Saved scene · used after refresh or restart':'Scene changed · confirm to save')};
 input.addEventListener('input',update);
 button.onclick=async()=>{const requested=input.value;button.disabled=true;status.textContent=tr('Saving scene…');
  try{const result=await api('/api/scene',{scene:requested,expected_scene:CFG.scene});CFG.scene=result.scene;if(input.value===requested)input.value=result.scene;update()}
  catch(e){button.disabled=false;status.textContent=tr(e.message)}
 };
 update();
}
function setupStation(c) {
  if(c.robot!=='franka')$('#killBtn').innerHTML='■ 提前结束当前模型<small>保留已录数据 · 回位后 A 继续 B，B 进入评分 <kbd>Esc</kbd></small>';
  if(c.feishu?.enabled){
    const fields=document.createElement('div');fields.className='row';fields.style.gap='12px';
    fields.innerHTML='<div style="flex:1"><label for="feishuDevice">Device number</label><select id="feishuDevice"><option value="">'+tr('Select device')+'</option>'+c.feishu.devices.map(d=>`<option value="${esc(d)}">${esc(d)}</option>`).join('')+'</select></div>';
    $('#scene').closest('.card').querySelector('details').insertAdjacentElement('beforebegin',fields);
  }
  $('#language').onclick=()=>{setLanguage(getLanguage()==='zh-CN'?'en':'zh-CN');if(parent!==window)parent.postMessage({type:'station-language',language:getLanguage()},location.origin)};
  $('#language').textContent=getLanguage()==='zh-CN'?'English':'中文';
  const people=[...new Set([...(c.evaluator_options||[]),...(c.people||[])])];
  $('#evaluator').innerHTML='<option value="">'+tr('Select evaluator')+'</option>'+people.map(p=>`<option value="${esc(p)}">${esc(p)}</option>`).join('');
  const labels={restart_policy:'Restart Policy',restart_docker:'Restart NUC Docker',restart_can:'Restart CAN'};
  $('#maintenance').innerHTML=(c.maintenance||[]).map(a=>`<button data-maintenance="${a}">${labels[a]}</button>`).join('');
  document.querySelectorAll('[data-maintenance]').forEach(b=>b.onclick=async()=>{
    $('#maintenanceStatus').textContent=tr('Working…');b.disabled=true;
    try{const r=await api('/api/maintenance/'+b.dataset.maintenance,{});$('#maintenanceStatus').textContent=r.msg||r.detail||r.error||tr(r.ok?'Completed':'Failed')}
    catch(e){$('#maintenanceStatus').textContent=e.message}finally{b.disabled=false}});
  $('#refreshServiceLogs').onclick=refreshTechnicalLogs;
  $('#technicalLogs').ontoggle=()=>{if($('#technicalLogs').open)refreshTechnicalLogs()};
  $('#statsRefresh').onclick=loadStats;$('#statsDate').onchange=loadStats;
  $('#reconcile').onclick=async()=>{try{await api('/api/reconcile',{});await loadStats();if(view==='review')loadEvals()}catch(e){toast(e.message)}};
  $('#keysUnlock').onclick=()=>{$('#keyInputs').disabled=false;$('#keysSave').disabled=false;$('#keysUnlock').disabled=true};
  if(c.robot==='franka') {
    const replacements={gpu:['Policy host GPU','Policy workers run on the Policy host.'],can:['Robot connection (RPC)','Check the NUC robot service.'],arms:['Robot service responds','Checks RPC without creating RobotEnv.'],cameras:['Cameras','Uses the existing calibrated UVC camera reader.'],server:['Policy Server','Runs on the Policy host; startup checks its health.']};
    for(const [key,[title,detail]] of Object.entries(replacements)) {
      const check=CHECKS.find(x=>x[0]===key);check[1]=title;check[2]=detail;
      $('#c-'+key+' h2').textContent=title;$('#d-'+key).textContent=detail;
    }
    const reset=$('[data-a="can_reset"]');reset.textContent='Restart NUC Docker';reset.onclick=()=>document.querySelector('[data-maintenance="restart_docker"]').click();
    $('[data-a="free_gpu"]').textContent='Recover Policy workers';
  }
  applyLanguage();
}

let logsLoading=false;
async function refreshTechnicalLogs(){
 if(logsLoading)return;logsLoading=true;
 try{const data=await api('/api/maintenance/logs');
  for(const name of ['client','policy']){const el=$('#'+name+'Log'),stick=el.scrollTop+el.clientHeight>=el.scrollHeight-20;
   el.textContent=data[name]||'';if(stick)el.scrollTop=el.scrollHeight}
  $('#logError').textContent=data.error||'';
 }catch(e){$('#logError').textContent=e.message}finally{logsLoading=false}
}
setInterval(()=>{if(document.querySelector('#technicalLogs')?.open)refreshTechnicalLogs()},2000);

function renderModelNames(){
 const names=ST.models||{};
 $('#runModels').textContent=['A','B'].map(side=>side+': '+(names[side]||tr('Model not available'))).join(' · ');
}

function bindPlayback(){
 const format=t=>Number.isFinite(t)?Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0'):'--:--';
 for(const side of ['A','B']){
  const videos=[...document.querySelectorAll(`video[data-side="${side}"]`)];
  const seek=document.querySelector(`[data-seek="${side}"]`);if(!videos.length||!seek)continue;
  const master=videos.find(v=>v.classList.contains('vmain'))||videos[0];
  videos.filter(v=>v!==master).forEach(v=>v.addEventListener('loadedmetadata',()=>{
   if(Number.isFinite(v.duration))v.currentTime=Math.min(master.currentTime,v.duration);
   v.playbackRate=master.playbackRate;
   if(!master.paused)v.play().catch(()=>{});
  }));
  const status=document.querySelector(`[data-playstate="${side}"]`);
  const update=()=>{
   if(!master.isConnected)return;
   const duration=master.duration,ready=Number.isFinite(duration)&&duration>0;
   seek.disabled=!ready;seek.max=ready?duration:0;seek.value=master.currentTime||0;
   document.querySelector(`[data-time="${side}"]`).textContent=format(master.currentTime)+' / '+format(duration);
   status.textContent=tr(master.error?'Video unavailable':master.ended?'Playback finished':!ready?'Loading video':master.paused?'Paused':'Playing');
  };
  for(const event of ['loadedmetadata','durationchange','timeupdate','play','pause','ended','error','seeked'])master.addEventListener(event,update);
  const play=()=>videos.forEach(v=>{const promise=v.play();if(promise)promise.catch(e=>{status.textContent=tr('Playback failed')+': '+e.message})});
  document.querySelector(`[data-play="${side}"]`).onclick=play;
  document.querySelector(`[data-pause="${side}"]`).onclick=()=>videos.forEach(v=>v.pause());
  document.querySelector(`[data-restart="${side}"]`).onclick=()=>{videos.forEach(v=>{v.currentTime=0});play()};
  document.querySelector(`[data-rate="${side}"]`).onchange=e=>videos.forEach(v=>v.playbackRate=+e.target.value);
  seek.oninput=()=>{videos.forEach(v=>{if(Number.isFinite(v.duration))v.currentTime=Math.min(+seek.value,v.duration)});update()};
  update();
 }
}

const translationOriginals=new Map();
function bindFeedbackTranslation(id){
 const fb=$('#fb'),btn=$('#translateBtn'),restore=$('#restoreTranslation');
 const key='colosseum-translation-original:'+STATION_KEY+':'+id;
 try{if(!translationOriginals.has(id)&&sessionStorage.getItem(key)!==null)translationOriginals.set(id,sessionStorage.getItem(key))}catch(e){}
 restore.hidden=!translationOriginals.has(id);
 restore.onclick=()=>{fb.value=translationOriginals.get(id);fb.dispatchEvent(new Event('input',{bubbles:true}))};
 btn.onclick=async()=>{
  const original=fb.value;
  if(!original.trim())return toast('Write an overall comment first');
  btn.disabled=true;btn.textContent=tr('Translating…');
  try{
   const result=await api('/api/translate',{text:original});
   if(!fb.isConnected)return;
   const modal=$('#translationDialog');
   $('#translationOriginal').textContent=original;$('#translationResult').value=result.text;
   $('#translationError').textContent='';modal.classList.add('on');
   $('#translationCancel').onclick=()=>modal.classList.remove('on');
   $('#translationUse').onclick=()=>{
    if(!fb.isConnected||fb.value!==original){$('#translationError').textContent=tr('The comment changed. Close this preview and translate the latest text.');return}
    const translated=$('#translationResult').value.trim();
    if(!translated){$('#translationError').textContent=tr('Translation is empty');return}
    translationOriginals.set(id,original);
    try{sessionStorage.setItem(key,original)}catch(e){}
    restore.hidden=false;fb.value=translated;fb.dispatchEvent(new Event('input',{bubbles:true}));
    modal.classList.remove('on');fb.focus();
   };
   applyLanguage();$('#translationResult').focus();
  }catch(e){toast(e.message)}finally{btn.disabled=false;btn.textContent=tr('Translate to English')}
 };
}

function openDiscard(id){
 const modal=$('#discardDialog'),button=$('#discardConfirm');
 $('#discardReason').value='';$('#discardError').textContent='';button.disabled=false;
 modal.classList.add('on');$('#discardReason').focus();
 $('#discardCancel').onclick=()=>modal.classList.remove('on');
 button.onclick=async()=>{
  const reason=$('#discardReason').value.trim();
  if(!reason){$('#discardError').textContent=tr('A reason is required to discard');return}
  button.disabled=true;
  try{const r=await api('/api/evals/'+id,{action:'discard',reason});
   toast(r.msg||'Discard started.');modal.classList.remove('on');loadEvals();pollBusy(id);
  }catch(e){$('#discardError').textContent=e.message}finally{button.disabled=false}
 };
 applyLanguage();
}
function openKeys() {
  if(CFG.settings_mode!=='host'&&ST) {
    const known=new Map((ST.keys||[]).map(row=>[row.provider,row]));
    ST.keys=['openai','xai','anthropic'].map(provider=>known.get(provider)||{provider,label:provider,source:''});
  }
  originalOpenKeys();
  if(CFG.settings_mode==='host') {
    $('#keyLocation').textContent='Franka credentials stay on the Policy host. Only the enabled providers can be selected here.';
    const active=new Set(CFG.managed_providers||[]);
    $('#keyInputs').innerHTML=['openai','xai','anthropic'].map(p=>`<label><input type="checkbox" style="width:auto" value="${p}" ${active.has(p)?'checked':''}> ${p}</label>`).join('');
  } else $('#keyLocation').textContent='Keys stay on this workstation. Leave a box empty to keep its saved key.';
  $('#keyInputs').disabled=true;$('#keysSave').disabled=true;$('#keysUnlock').disabled=false;
  applyLanguage();
}
async function loadStats() {
  try {
    const date=$('#statsDate').value;
    const stats=await api('/api/stats'+(date?'?date='+encodeURIComponent(date):''));
    $('#statsRows').innerHTML=stats.rows.map(r=>`<tr><td>${esc(r.date)}</td><td data-user-text>${esc(r.person)}</td><td>${esc(r.robot)}</td><td>${r.count}</td></tr>`).join('')||'<tr><td colspan="4">No confirmed submissions in this period.</td></tr>';
    $('#statsSummary').textContent=tr('Confirmed A/B pairs: ')+stats.rows.reduce((n,r)=>n+r.count,0);
    let panel=$('#feishuStats');
    if(CFG.feishu?.enabled){
      if(!panel){panel=document.createElement('div');panel.id='feishuStats';$('#statsSummary').closest('.card').append(panel)}
      const rows=stats.feishu_reports||[];
      panel.innerHTML='<h3>'+tr('Original Feishu form')+'</h3><p>'+tr('Feishu confirmed: ')+rows.filter(r=>r.status==='sent').length+'</p><table class="stats-table"><thead><tr><th>'+tr('Date')+'</th><th>'+tr('Person')+'</th><th>'+tr('Evaluation')+'</th><th>'+tr('Feishu status')+'</th></tr></thead><tbody>'+rows.map(r=>
        `<tr><td>${esc(r.date)}</td><td data-user-text>${esc(r.person)}</td><td data-user-text>${esc(r.id)}</td><td>${esc(feishuLabel(r.status))}${r.error?'<br><span>'+esc(tr(r.error))+'</span>':''}${['error','unknown'].includes(r.status)?`<br><button type="button" class="small" data-feishu-retry="${esc(r.id)}" data-unknown="${r.status==='unknown'}">${tr('Retry Feishu only')}</button>`:''}</td></tr>`).join('')+'</tbody></table>';
      panel.querySelectorAll('[data-feishu-retry]').forEach(button=>button.onclick=async()=>{
        const unknown=button.dataset.unknown==='true';
        if(unknown&&!confirm('Check the original Feishu table first. Is this evaluation absent? Only continue if it has not been submitted.'))return;
        button.disabled=true;
        try{await api('/api/evals/'+encodeURIComponent(button.dataset.feishuRetry)+'/feishu',{checked_missing:unknown});await loadStats()}
        catch(e){toast(e.message);button.disabled=false}
      });
    }
    applyLanguage();
  }catch(e){toast(e.message)}
}
function feishuLabel(status){return tr({queued:'Waiting for Feishu',preparing:'Preparing Feishu submission',sending:'Submitting to Feishu',sent:'Feishu submitted',error:'Feishu failed',unknown:'Feishu confirmation unknown',not_enabled:'Feishu not enabled for this evaluation'}[status]||status)}
setInterval(()=>{if(typeof view!=='undefined'&&view==='stats'&&CFG.feishu?.enabled)loadStats()},5000);

// Grow the embedded page so only the outer document scrolls. Keep station
// contexts alive; resizing never starts/stops preview, recording or playback.
if(parent!==window){
 let scheduled=false,lastHeight=0;
 const publishHeight=()=>{
  scheduled=false;
  const main=document.querySelector('main');
  if(!main?.offsetWidth)return;
  const height=Math.max(500,Math.ceil(main.getBoundingClientRect().bottom+scrollY));
  if(height!==lastHeight){lastHeight=height;parent.postMessage({type:'station-height',height},location.origin)}
 };
 const scheduleHeight=()=>{if(!scheduled){scheduled=true;requestAnimationFrame(publishHeight)}};
 const observer=new ResizeObserver(scheduleHeight);
 for(const element of document.querySelectorAll('header,main'))observer.observe(element);
 addEventListener('resize',scheduleHeight);
 addEventListener('message',event=>{
  if(event.origin!==location.origin||event.source!==parent)return;
  if(event.data?.type==='hub-visible'){lastHeight=0;scheduleHeight()}
  if(event.data?.type==='hub-viewport'){
   const {top,height}=event.data;
   if(!Number.isFinite(top)||top<0||!Number.isFinite(height)||height<=0)return;
   document.documentElement.classList.add('embedded');
   document.documentElement.style.setProperty('--hub-visible-top',top+'px');
   document.documentElement.style.setProperty('--hub-visible-height',height+'px');
   if(Number.isFinite(event.data.viewportHeight)&&event.data.viewportHeight>0)document.documentElement.style.setProperty('--hub-window-height',event.data.viewportHeight+'px');
  }
 });
 scheduleHeight();
}

let reviewLayoutCleanup=()=>{};
function bindReviewLayout(id){
 reviewLayoutCleanup();
 const player=document.querySelector('#reviewPlayer');if(!player)return;
 const panels=[...player.querySelectorAll('[data-review-panel]')],tabs=[...player.querySelectorAll('[data-review-side]')];
 const key='review-camera-side:'+STATION_KEY+':'+id;
 let scheduled=0;
 const fit=()=>{
  scheduled=0;if(!player.isConnected||!player.offsetWidth)return;
  const panel=panels.find(p=>!p.hidden),cameras=panel?.querySelector('.review-cameras');if(!cameras)return;
  const style=getComputedStyle(document.documentElement);
  const viewport=parseFloat(style.getPropertyValue('--hub-window-height'))||parseFloat(style.getPropertyValue('--hub-visible-height'))||innerHeight;
  const overhead=player.getBoundingClientRect().height-cameras.getBoundingClientRect().height;
  const count=Number(cameras.dataset.cameraCount),width=cameras.clientWidth;
  const natural=count===1?width*.75:count===2?width*.375:matchMedia('(max-width:700px)').matches?width*1.125+8:width/2;
  const height=Math.floor(Math.max(100,Math.min(620,natural,viewport-overhead-24)))+'px';
  if(cameras.style.height!==height)cameras.style.height=height;
 };
 const schedule=()=>{if(!scheduled)scheduled=requestAnimationFrame(fit)};
 const select=(side,scroll=false)=>{
  if(typeof pauseReviewPlayback==='function')pauseReviewPlayback();
  else player.querySelectorAll('video').forEach(video=>video.pause());
  for(const panel of panels)panel.hidden=panel.dataset.reviewPanel!==side;
  for(const tab of tabs){const active=tab.dataset.reviewSide===side;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1}
  try{sessionStorage.setItem(key,side)}catch(e){}
  fit();if(scroll)requestAnimationFrame(()=>player.scrollIntoView({block:'start'}));
 };
 for(const tab of tabs)tab.onclick=()=>select(tab.dataset.reviewSide,true);
 player.querySelector('[role=tablist]').onkeydown=event=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();const current=tabs.findIndex(t=>t.getAttribute('aria-selected')==='true');
  const index=event.key==='Home'?0:event.key==='End'?tabs.length-1:(current+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  select(tabs[index].dataset.reviewSide,true);tabs[index].focus();
 };
 const observer=new ResizeObserver(schedule);observer.observe(player);
 const viewportChanged=event=>{if(event.origin===location.origin&&event.source===parent&&event.data?.type==='hub-viewport')schedule()};
 addEventListener('resize',schedule);addEventListener('message',viewportChanged);
 reviewLayoutCleanup=()=>{observer.disconnect();cancelAnimationFrame(scheduled);removeEventListener('resize',schedule);removeEventListener('message',viewportChanged)};
 let selected;try{selected=sessionStorage.getItem(key)}catch(e){}
 select(tabs.some(t=>t.dataset.reviewSide===selected)?selected:tabs[0]?.dataset.reviewSide);
}
