/* Each station owns a persistent frame and a fixed request prefix. Selection is per tab. */
const H=s=>document.querySelector(s),hx=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hubAPI=async(path,body)=>{const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();if(!r.ok)throw Error(j.detail||r.statusText);return j};
let stations=[],selected='',editing=null,refreshing=false;
const stationFrames=new Map();
try{selected=new URLSearchParams(location.search).get('station')||sessionStorage.getItem('selected-workstation')||''}catch(e){}
function phaseLabel(s){return !s.online?'Offline':s.prompt?'Waiting for you':s.recording?'Running':s.pending?'To review':'Online'}
function renderStations(){
 H('#robotPicker').innerHTML=stations.map(s=>`<option value="${s.id}">${hx(s.name)} · ${tr(phaseLabel(s))}</option>`).join('');
 H('#robotPicker').value=selected;
 H('#robotStatuses').innerHTML=stations.map(s=>`<button data-station="${s.id}" class="${s.id===selected?'active':''}"><span class="${s.online?'dot':'offline'}">●</span> <span data-user-text>${hx(s.name)}</span> · <span>${phaseLabel(s)}</span></button>`).join('');
 H('#robotStatuses').querySelectorAll('button').forEach(b=>b.onclick=()=>selectStation(b.dataset.station));
 applyLanguage();
}
function selectStation(id){
 const station=stations.find(s=>s.id===id);if(!station)return;
 selected=id;try{sessionStorage.setItem('selected-workstation',id)}catch(e){}
 const url=new URL(location.href);url.searchParams.set('station',id);history.replaceState(null,'',url);
 if(!stationFrames.has(id)&&station.online){
  const frame=document.createElement('iframe');frame.title=station.name;frame.dataset.station=id;
  const initialHash=['#setup','#record','#review','#stats'].includes(location.hash)?location.hash:'#setup';
  // Always open Setup on a newly selected robot; a previous robot's Record view must not start its preview.
  frame.src='/s/'+id+'/'+(stationFrames.size===0&&station.local?initialHash:'#setup');
  frame.addEventListener('load',()=>frame.contentWindow.postMessage({type:'hub-language',language:getLanguage()},location.origin));
  stationFrames.set(id,frame);H('#frames').append(frame);
 }
 for(const [sid,frame] of stationFrames){frame.hidden=sid!==id;if(frame.hidden)frame.contentWindow.postMessage({type:'hub-hidden'},location.origin)}
 H('#offlinePanel').hidden=stationFrames.has(id);H('#offlineName').textContent=station.name;
 H('#hubError').textContent=station.online?'':tr(station.error||'Workstation unavailable or not yet running the compatible UI');
 renderStations();
}
async function refreshStations(){
 if(refreshing)return;refreshing=true;
 try{const data=await hubAPI('/hub/stations');stations=data.items;
  if(!stations.some(s=>s.id===selected))selected=data.local_id;
  selectStation(selected);
 }catch(e){H('#hubError').textContent=e.message}finally{refreshing=false}
}
function openRobotDialog(row=null){
 editing=row;H('#robotDialogTitle').textContent=row?'Edit robot':'Add robot';
 H('#robotName').value=row?.name||'';H('#robotAddress').value=row?.url||'';
 H('#robotAddress').disabled=!!row?.local;H('#robotAddress').required=!row?.local;
 H('#robotFormError').textContent='';H('#robotDialog').hidden=false;applyLanguage();H('#robotName').focus();
}
H('#addRobot').onclick=()=>openRobotDialog();
H('#editRobot').onclick=()=>openRobotDialog(stations.find(s=>s.id===selected));
H('#robotCancel').onclick=()=>H('#robotDialog').hidden=true;
H('#robotForm').onsubmit=async e=>{
 e.preventDefault();const button=H('#robotSave');button.disabled=true;
 try{
  const row=await hubAPI('/hub/stations',{name:H('#robotName').value,address:H('#robotAddress').value,...(editing?{id:editing.id}:{})});
  // An explicit address edit creates a new browsing context, while the remote evaluation keeps running.
  if(editing&&editing.url!==row.url&&stationFrames.has(row.id)){stationFrames.get(row.id).remove();stationFrames.delete(row.id)}
  selected=row.id;H('#robotDialog').hidden=true;await refreshStations();
 }catch(error){H('#robotFormError').textContent=tr(error.message)}finally{button.disabled=false}
};
H('#robotPicker').onchange=e=>selectStation(e.target.value);
H('#retryRobot').onclick=refreshStations;
H('#language').onclick=()=>{
 setLanguage(getLanguage()==='zh-CN'?'en':'zh-CN');renderStations();
 for(const frame of stationFrames.values())frame.contentWindow.postMessage({type:'hub-language',language:getLanguage()},location.origin);
};
async function loadHubStats(){
 H('#hubStatsNotice').textContent=tr('Loading…');
 try{
  const date=H('#hubStatsDate').value;
  const result=await hubAPI('/hub/statistics'+(date?'?date='+encodeURIComponent(date):''));
  const offline=result.sources.filter(s=>!s.available).map(s=>s.name);
  H('#hubStatsNotice').textContent=tr('Confirmed A/B pairs: ')+result.rows.reduce((n,r)=>n+r.count,0)+(offline.length?' · '+tr('Unavailable: ')+offline.join(', '):'');
  H('#hubStatsRows').innerHTML=result.rows.map(r=>`<tr><td>${hx(r.date)}</td><td data-user-text>${hx(r.person)}</td><td data-user-text>${hx(r.station_name)}</td><td>${r.count}</td></tr>`).join('');
 }catch(e){H('#hubStatsNotice').textContent=e.message}
}
H('#allStats').onclick=()=>{H('#allStatsDialog').hidden=false;loadHubStats()};
H('#allStatsClose').onclick=()=>H('#allStatsDialog').hidden=true;
H('#hubStatsRefresh').onclick=loadHubStats;H('#hubStatsDate').onchange=loadHubStats;
window.addEventListener('message',event=>{
 if(event.origin!==location.origin||![...stationFrames.values()].some(f=>f.contentWindow===event.source))return;
 if(event.data?.type==='station-language'){
  setLanguage(event.data.language);renderStations();
  for(const frame of stationFrames.values())if(frame.contentWindow!==event.source)frame.contentWindow.postMessage({type:'hub-language',language:getLanguage()},location.origin);
 }
});
setLanguage(getLanguage());refreshStations();setInterval(refreshStations,8000);
