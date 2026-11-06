"""Reapply the small structural changes to the preserved original UI."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
s = (root / 'upstream/eval_gui.html').read_text(encoding='utf-8')
s = s.replace('<html lang="en">', '<html lang="zh-CN">')
s = s.replace('</style>', '''
fieldset{border:0;margin:0;padding:0}fieldset:disabled{opacity:.48}
.station-tools{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.stats-table{width:100%;border-collapse:collapse}
.stats-table td,.stats-table th{text-align:left;padding:12px;border-bottom:1px solid var(--line)}
@media(max-width:700px){header .bar{flex-wrap:wrap}.station-tools{width:100%}.stats-table{font-size:13px}
header .steps{width:100%;display:grid;grid-template-columns:repeat(2,1fr)}header .steps button{white-space:nowrap;justify-content:flex-start}.steps .n{flex-shrink:0}}
</style>''', 1)
s = s.replace('<div class="pill glass" id="srvpill">', '<button class="small" id="language" type="button">English</button><div class="pill glass" id="srvpill">')
s = s.replace('  </nav>', '    <button data-v="stats"><span class="n">4</span>Statistics</button>\n  </nav>', 1)
s = s.replace('  <div class="grid checks" id="checks"></div>', '''  <div class="grid checks" id="checks"></div>
  <div class="card"><h2>Station maintenance</h2><p class="mut">Uses the existing station maintenance commands. Restarting interrupts the current evaluation.</p>
  <div class="station-tools" id="maintenance"></div><p id="maintenanceStatus" role="status"></p>
  <details class="log"><summary>Service logs</summary><button id="refreshServiceLogs" class="small">Refresh</button><pre id="serviceLogs"></pre></details></div>''')
s = s.replace('<input id="evaluator" placeholder="optional">', '<input id="evaluator" list="peopleOptions" placeholder="Select or enter your name" autocomplete="off"><datalist id="peopleOptions"></datalist>')
s = s.replace('</main>', '''<section class="view" id="v-stats"><div class="hero"><div><div class="eyebrow">Local workstation · Beijing time</div><h1>Daily <em>evaluations</em>.</h1>
<p class="lead">One A/B pair counts once after score submission is confirmed. Later dataset uploads do not change this count.</p></div></div>
<div class="card"><div class="station-tools"><label for="statsDate">Date</label><input type="date" id="statsDate" style="width:auto"><button id="statsRefresh">Refresh</button><button id="reconcile">Check pending confirmations</button></div>
<p id="statsSummary" role="status"></p><table class="stats-table"><thead><tr><th>Date</th><th>Person</th><th>Robot</th><th>A/B pairs</th></tr></thead><tbody id="statsRows"></tbody></table>
<p class="mut">Statistics are read-only. All people on this workstation are visible. Other workstations are not aggregated in v1.</p></div></section></main>''')
s = s.replace('<p class="mut" style="margin:0">Keys stay on this computer, in <code>local/llm-keys.env</code>. Leave a box empty to keep its saved key.</p>', '<p class="mut" id="keyLocation">Leave a box empty to keep its saved key.</p><button id="keysUnlock" class="small">Unlock settings</button>')
s = s.replace('<div id="keyInputs"></div>', '<fieldset id="keyInputs" disabled></fieldset>')
s = s.replace('<script>\nconst $=', '<script src="/i18n.js"></script>\n<script src="/station.js"></script>\n<script>\nconst $=', 1)
s = s.replace("if(v=='review')loadEvals();", "if(v=='review')loadEvals(); if(v=='stats')loadStats();")
s = s.replace('const api=(p,b)=>', 'const api=(p,b)=>')
s = s.replace('e.textContent=t;', 'e.textContent=tr(t);')
s = s.replace("async function loadResumable(){\n  const evs=await api('/api/evals').catch(()=>[]);", "async function loadResumable(){\n  const evs=await allEvaluations();")
s = s.replace("const pend=evs.filter(e=>e.state=='review'||e.state=='scored');", "const pend=evs.filter(e=>e.managed&&!['submitted','discarded'].includes(e.state));")
s = s.replace('Starting a new evaluation closes it on the Router.', 'Submit or discard this A/B pair before starting the next one.')
s = s.replace('<b>“${esc(pend[0].instruction)}” is recorded but not submitted.</b>', '<b><span data-user-text>“${esc(pend[0].instruction)}”</span> is recorded but not submitted.</b>')
s = s.replace('Scene: ${esc(d.scene)||\'–\'} ·', '<span>Scene:</span> <span data-user-text>${esc(d.scene)||\'–\'}</span> ·')
s = s.replace("  const all=await api('/api/evals').catch(()=>[]);", "  const all=await allEvaluations();")
s = s.replace("e=>e.state=='review'||e.state=='scored'", "e=>['review','scored','unknown','submitting'].includes(e.state)")
s = s.replace("const LBL={review:", "const LBL={unknown:'confirmation pending',submitting:'submitting',discarding:'discarding',review:")
s = s.replace("const ws=new WebSocket(`ws://${location.host}/ws`)", "const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`)")
s = s.replace("['setup','record','review'].includes", "['setup','record','review','stats'].includes")
s = s.replace("api('/api/config').then(c=>{CFG=c;", "api('/api/config').then(c=>{CFG=c;setupStation(c);")
s = s.replace("function openKeys(){", "function originalOpenKeys(){")
s = s.replace("function openKeys(){", "function originalOpenKeys(){")
s = s.replace("$('#keysSave').onclick=()=>{const body={};", "$('#keysSave').onclick=()=>{if($('#keyInputs').disabled)return;const body={};")
s = s.replace("api('/api/keys',body).then", "api('/api/keys',CFG.settings_mode==='host'?{llm_providers:[...document.querySelectorAll('#keyInputs input:checked')].map(i=>i.value)}:body).then")
s = s.replace("then(()=>{$('#keysModal').classList.remove('on');toast('Saved. Checking each key…')})", "then(async()=>{CFG=await api('/api/config');$('#keysModal').classList.remove('on');toast('Saved. Checking each key…')})")
s = s.replace("toast('Submitting… videos are uploading.')", "toast(r.msg||'Submitting scores…')")
s = s.replace('Sending to the Router… this can take a few minutes while videos upload.', 'Submitting scores. Dataset upload follows the station configuration.')
s = s.replace('Scores, feedback, videos and the dataset become public and cannot be edited.', 'Scores and feedback are submitted now. Dataset upload follows the station configuration. Continue?')
s = s.replace("const banner={submitted:", "const banner={unknown:'<div class=\"banner warn\">Submission confirmation is pending. Check Router status before retrying.</div>',submitting:'<div class=\"banner info\">Submitting scores…</div>',submitted:")
# Mark user-authored text so language changes never translate their task or observations.
s = s.replace('id="runTask"', 'data-user-text id="runTask"').replace('<div class="t">${esc(e.instruction)', '<div class="t" data-user-text>${esc(e.instruction)')
s = s.replace('var(--serif);margin-top:4px">${esc(d.instruction)}', 'var(--serif);margin-top:4px" data-user-text>${esc(d.instruction)}')
# Feedback from the first YAM hardware run: retain original structure and controls.
s = s.replace('<input id="evaluator" list="peopleOptions" placeholder="Select or enter your name" autocomplete="off"><datalist id="peopleOptions"></datalist>',
              '<select id="evaluator"><option value="">Select evaluator</option></select>')
s = s.replace('<div class="timeline" id="timeline"></div>',
              '<div id="runModels" data-user-text style="margin-top:12px;overflow-wrap:anywhere"></div><div class="timeline" id="timeline"></div>')
s = s.replace("  const lg=$('#log'),txt=ST.log.join('\\n');", "  renderModelNames();\n  const lg=$('#log'),txt=ST.log.join('\\n');")
s = s.replace('<details class="log"><summary>Service logs</summary><button id="refreshServiceLogs" class="small">Refresh</button><pre id="serviceLogs"></pre></details>', '')
s = s.replace('</main>', '''<details class="log" id="technicalLogs"><summary>Client / Policy technical logs</summary>
<button id="refreshServiceLogs" class="small">Refresh</button><span id="logError" role="status"></span>
<h3>Client</h3><pre id="clientLog"></pre><h3>Policy</h3><pre id="policyLog"></pre></details></main>
<div class="modal" id="discardDialog" role="dialog" aria-modal="true" aria-labelledby="discardTitle"><div class="card">
<h2 id="discardTitle">Discard evaluation</h2><p>Close this evaluation without submitting scores. Recording files are kept.</p>
<label for="discardReason">Reason for discarding</label><textarea id="discardReason"></textarea>
<p id="discardError" role="alert"></p><div class="row"><button id="discardCancel">Cancel</button><button id="discardConfirm">Confirm discard</button></div>
</div></div>''')
s = s.replace('<span class="chip ${r.side}" style="font-size:13px">Policy ${r.side}</span>',
              '<div><span class="chip ${r.side}" style="font-size:13px">Policy ${r.side}</span><div data-user-text style="overflow-wrap:anywhere">${esc(r.model_name||tr("Model not available"))}</div></div>')
s = s.replace('    ${stopNote(r.stop)}', '''    ${r.recorded?`<div class="playback" data-playback="${r.side}" style="margin-top:12px"><input type="range" data-seek="${r.side}" min="0" max="0" value="0" step="0.01" disabled aria-label="Playback position"><div class="spread"><span data-time="${r.side}">0:00 / --:--</span><span data-playstate="${r.side}" role="status">Loading video</span></div></div>`:''}
    ${stopNote(r.stop)}''')
start = s.index('  const V=s=>document.querySelectorAll(`video[data-side=')
end = s.index('  for(const r of d.runs)', start)
s = s[:start] + '  bindPlayback();\n' + s[end:]
start = s.index("  $('#discardBtn').onclick=()=>{const reason=prompt(")
end = s.index('\n}', start)
s = s[:start] + "  $('#discardBtn').onclick=()=>openDiscard(id);" + s[end:]
# Single overall comment; omit old notes/factors from writes so saved history survives.
start = s.index('    <label>What did ${r.side} do?')
end = s.index('    <label>How much of the task', start)
s = s[:start] + s[end:]
start = s.index('    <div class="card" style="margin-top:16px"><h2 style="font:500 26px var(--serif)">Compare the policies')
end = s.index('    <div class="card" style="margin-top:16px"><label style="margin-top:0">Which policy', start)
s = s[:start] + s[end:]
s = s.replace('Overall feedback <span style="text-transform:none;font-weight:400">· English, sent to the Router</span>', 'Overall feedback <span style="text-transform:none;font-weight:400">· Required</span>')
s = s.replace("${locked?'':'<button class=\"small primary\" id=\"genBtn\">✨ Write from my observations</button>'}",
              "${locked||CFG.feedback_generation_enabled!==true?'':'<button class=\"small primary\" id=\"genBtn\">✨ Polish overall comment</button>'}")
s = s.replace('Write your observations for A and B above, then click “Write from my observations”. You can edit the result.', 'Describe how A and B performed. Required before submitting.')
s = s.replace('id="fb" style=', 'id="fb" aria-required="true" style=')
s = s.replace("if(!$('#fb').value.trim()&&!confirm('Submit without any feedback text?'))return;", "if(!$('#fb').value.trim()){$('#fb').focus();return toast('Overall feedback is required before submitting')}")
start = s.index("  const fcount=()=>")
end = s.index("  document.querySelectorAll('[data-pref]')", start)
s = s[:start] + s[end:]
start = s.index("  const body=action=>")
end = s.index('  if(locked)return;', start)
s = s[:start] + '''  const body=action=>({action,preference:pref,feedback:$('#fb').value,
    ...Object.fromEntries(d.runs.map(r=>['score_'+r.side,$('#sc-'+r.side)?.value??'']))});
''' + s[end:]
s = s.replace("  $('#genBtn').onclick=async()=>{", "  if($('#genBtn'))$('#genBtn').onclick=async()=>{")
s = s.replace("const b=body('save');if(!Object.values(b.notes).some(x=>x.trim()))return toast('Write a few observations for each policy first.');", "const b=body('save');if(!b.feedback.trim())return toast('Write an overall comment first');")
s = s.replace("    if(FACT.some(([f])=>!factors[f]))return toast('Select one option for every factor under “Compare the policies”.');\n", '')
s = s.replace("btn.textContent='✨ Write from my observations'", "btn.textContent='✨ Polish overall comment'")
initial_view = "show(['setup','record','review','stats'].includes(location.hash.slice(1))?location.hash.slice(1):'setup');"
s = s.replace('    <textarea id="fb"', '''    ${locked?'':'<div class="row"><button type="button" class="small" id="translateBtn">Translate to English</button><button type="button" class="small" id="restoreTranslation" hidden>Restore original comment</button></div>'}
    <textarea id="fb"''')
s = s.replace('  if(locked)return;', '  if(locked)return;\n  bindFeedbackTranslation(id);')
s = s.replace('</main>', '''</main>
<div class="modal" id="translationDialog" role="dialog" aria-modal="true" aria-labelledby="translationTitle"><div class="card" style="max-height:85vh;overflow:auto;background:var(--bg)">
<h2 id="translationTitle">Review English translation</h2>
<label>Original comment</label><pre id="translationOriginal" data-user-text style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>
<label for="translationResult">English translation</label><textarea id="translationResult" style="min-height:140px"></textarea>
<p>Check the translation before using it. Your original is kept in this browser tab.</p>
<p id="translationError" role="alert"></p>
<div class="row"><button type="button" id="translationCancel">Cancel</button><button type="button" class="primary" id="translationUse">Use translation</button></div>
</div></div>''')
s = s.replace(initial_view+'\n', '')
s = s.replace("$('#maxsteps').value=c.max_steps;connect()});", "$('#maxsteps').value=c.max_steps;connect();"+initial_view+"});")
# Every iframe is permanently bound to one workstation. Never use a global mutable target.
s = s.replace('Statistics are read-only. All people on this workstation are visible. Other workstations are not aggregated in v1.',
              'Statistics are read-only. This page shows the current workstation. Use All robots statistics in the top bar for the combined view.')
s = s.replace('fetch(p,b===undefined?', 'fetch(stationURL(p),b===undefined?')
s = s.replace('src="/api/thumb/', 'src="${STATION_BASE}/api/thumb/')
s = s.replace('src="/video/', 'src="${STATION_BASE}/video/')
s = s.replace('${location.host}/ws', '${location.host}${STATION_BASE}/ws')
s = s.replace("'evform'", "'evform:'+STATION_KEY").replace("'evfilter'", "'evfilter:'+STATION_KEY")
s = s.replace("$('#maxsteps').value=c.max_steps;connect();", "$('#maxsteps').value=c.max_steps;bindStationFormDraft();connect();")
s = s.replace('  if(locked)return;\n  bindFeedbackTranslation(id);',
              '  if(locked){clearReviewDraft(id);return;}\n  bindReviewDraft(id,d);\n  bindFeedbackTranslation(id);')
s = s.replace("then(r=>{toast(r.msg);loadEvals()}).catch(e=>toast(e.message));", "then(r=>{clearReviewDraft(id);toast(r.msg);loadEvals()}).catch(e=>toast(e.message));")
(root / 'eval_gui.html').write_text(s, encoding='utf-8')
