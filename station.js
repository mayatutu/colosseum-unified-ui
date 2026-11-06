/* Original UI extension; no replacement recording or review state machine. */
const stationPath=location.pathname.split('/').filter(Boolean);
const STATION_BASE=stationPath.length===2&&stationPath[0]==='s'?'/s/'+stationPath[1]:'';
const STATION_KEY=STATION_BASE||'local';
function stationURL(path){return STATION_BASE+path}
function readDraft(key){try{return JSON.parse(sessionStorage.getItem(key)||'null')}catch(e){return null}}
function writeDraft(key,value){try{sessionStorage.setItem(key,JSON.stringify(value))}catch(e){}}
function bindStationFormDraft(){
 const ids=['instruction','scene','evaluator','maxsteps'],key='station-form:'+STATION_KEY,saved=readDraft(key);
 if(saved)for(const id of ids)if(saved[id]!==undefined)$('#'+id).value=saved[id];
 const save=()=>writeDraft(key,Object.fromEntries(ids.map(id=>[id,$('#'+id).value])));
 for(const id of ids){$('#'+id).addEventListener('input',save);$('#'+id).addEventListener('change',save)}
}
function clearReviewDraft(id){try{sessionStorage.removeItem('station-review:'+STATION_KEY+':'+id)}catch(e){}}
function bindReviewDraft(id,d){
 const key='station-review:'+STATION_KEY+':'+id;
 const baseline=JSON.stringify([d.feedback,d.preference,d.runs.map(r=>[r.side,r.score])]);
 const saved=readDraft(key);
 if(saved?.baseline===baseline){
  $('#fb').value=saved.feedback;pref=saved.preference;
  for(const side of ['A','B'])if($('#sc-'+side)){$('#sc-'+side).value=saved['score_'+side];$('#rg-'+side).value=saved['score_'+side]||0}
  document.querySelectorAll('[data-pref]').forEach(b=>b.classList.toggle('on',b.dataset.pref===pref));
 }else if(saved)clearReviewDraft(id);
 const save=()=>writeDraft(key,{baseline,feedback:$('#fb').value,preference:pref,
  score_A:$('#sc-A')?.value||'',score_B:$('#sc-B')?.value||''});
 for(const el of document.querySelectorAll('#fb,#sc-A,#sc-B,#rg-A,#rg-B'))el.addEventListener('input',save);
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
    const page=await api(`/api/evals?paginated=true&offset=${offset}&limit=100`);
    items.push(...page.items);offset+=page.items.length;
    if(!page.items.length||offset>=page.total) return items;
  }
}
function setupStation(c) {
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
    applyLanguage();
  }catch(e){toast(e.message)}
}
