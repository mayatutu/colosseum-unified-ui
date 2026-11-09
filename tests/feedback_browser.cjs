// Offline browser fixtures only. No real evaluation is submitted or discarded.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const out=path.resolve(__dirname,'../validation');
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1080}});
  const errors=[],writes=[],dialogs=[];let discarded=false,translationFail=false,translationDelay=0;
  const translationCalls=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',async d=>{dialogs.push(d.type());await d.dismiss()});
  const fixture={id:'offline_feedback_fixture',instruction:'Offline fixture — not a real evaluation',scene:'test',state:'review',
   time:1700000000,busy:false,managed:true,preference:'',feedback:'',factors:{},log:'',
   runs:['A','B'].map(side=>({id:'test_'+side,side,model_name:side==='A'?'lingbot-yam':'grok-4.7',recorded:true,
    cams:['head_image','left_image','right_image'],stop:null,notes:'',score:null}))};
  await page.route('**/api/**',async route=>{
   const r=route.request(),url=new URL(r.url());let data={};
   if(r.method()==='POST'){
    if(url.pathname==='/api/translate'){
     translationCalls.push(r.postDataJSON());
     if(translationDelay)await new Promise(resolve=>setTimeout(resolve,translationDelay));
     return route.fulfill({status:translationFail?502:200,json:translationFail?
      {detail:'Translation failed. Your original comment is unchanged.'}:{text:'A completed the task, but B did not.'}});
    }
    const body=r.postDataJSON();writes.push(body);
    assert(['save','discard'].includes(body.action));
    if(body.action==='discard')discarded=true;
    data={msg:body.action==='discard'?'Discard started.':'Draft saved.'};
   }else if(url.pathname==='/api/config')data={robot:'yam',station:'yam',institution:'OFFLINE TEST',people:[],
    evaluator_options:Array.from({length:10},(_,i)=>'T'+i),settings_mode:'keys',maintenance:[],max_steps:800};
   else if(url.pathname==='/api/maintenance/logs')data={client:'Client fixture log\n',policy:'Policy fixture log\n',error:''};
   else if(url.pathname==='/api/evals')data={items:[{...fixture,state:discarded?'discarded':'review'}],total:1,offset:0,limit:100};
   else if(url.pathname.startsWith('/api/evals/'))data={...fixture,state:discarded?'discarded':'review'};
   await route.fulfill({json:data});
  });
  await page.route('**/video/**',route=>{
   const bytes=fs.readFileSync(path.join(out,'feedback-test-video.mp4'));
   const range=route.request().headers()['range']?.match(/bytes=(\d+)-(\d*)/);
   const start=range?+range[1]:0,end=range&&range[2]?Math.min(+range[2],bytes.length-1):bytes.length-1;
   return route.fulfill({status:range?206:200,contentType:'video/mp4',body:bytes.subarray(start,end+1),
    headers:{'Accept-Ranges':'bytes','Content-Length':String(end-start+1),...(range?{'Content-Range':`bytes ${start}-${end}/${bytes.length}`}:{})}});
  });
  await page.goto('http://127.0.0.1:8870/station#review',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>typeof ST!=='undefined'&&ST!==null);
  assert.equal(await page.locator('#evaluator').evaluate(e=>e.tagName),'SELECT');
  assert.deepEqual(await page.locator('#evaluator option').allTextContents(),['请选择评测人员',...Array.from({length:10},(_,i)=>'T'+i)]);
  await page.waitForFunction(()=>document.querySelector('[data-seek="A"]')?.disabled===false);
  assert((await page.locator('#evdetail').textContent()).includes('grok-4.7'));
  await page.evaluate(()=>{ST.models={A:'lingbot-yam',B:'grok-4.7'};renderModelNames()});
  assert((await page.locator('#runModels').textContent()).includes('grok-4.7'));
  await page.locator('[data-seek="A"]').evaluate(e=>{e.value=1.25;e.dispatchEvent(new Event('input'))});
  await page.waitForFunction(()=>[...document.querySelectorAll('video[data-side="A"]')].every(v=>Math.abs(v.currentTime-1.25)<.15),null,{timeout:5000}).catch(async e=>{
   console.log(await page.locator('video[data-side="A"]').evaluateAll(vs=>vs.map(v=>({time:v.currentTime,duration:v.duration,state:v.readyState,error:v.error?.message}))));throw e;
  });
  const times=await page.locator('video[data-side="A"]').evaluateAll(vs=>vs.map(v=>v.currentTime));
  assert(times.every(t=>Math.abs(t-1.25)<.15));
  await page.locator('[data-play="A"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-playstate="A"]').textContent==='已播放结束');
  await page.screenshot({path:path.join(out,'feedback-playback-fixture.png'),fullPage:true});
  assert.equal(await page.locator('#ob-A,#ob-B,[data-f],#genBtn').count(),0);
  await page.locator('[data-review-side="A"]').click();await page.locator('#sc-A').fill('100');await page.locator('[data-review-side="B"]').click();await page.locator('#sc-B').fill('50');
  await page.locator('[data-pref="A"]').click();
  assert.equal(await page.locator('#fb').getAttribute('aria-required'),'true');
  await page.locator('#fb').fill('   ');
  await page.locator('#submitBtn').click();
  assert.equal(writes.length,0);
  assert((await page.locator('#toast').textContent()).includes('请先填写综合评语'));
  // Translation previews do not save or submit; cancellation/failure preserve input.
  const original='A 完成了任务，B 没完成。';
  await page.locator('#fb').fill(original);
  await page.locator('#translateBtn').click();
  await page.waitForSelector('#translationDialog.on');
  assert.equal(await page.locator('#fb').inputValue(),original);
  assert.equal(await page.locator('#translationOriginal').textContent(),original);
  assert.equal(await page.locator('#translationTitle').textContent(),'确认英文译文');
  await page.locator('#language').evaluate(el=>el.click());
  assert.equal(await page.locator('#translationTitle').textContent(),'Review English translation');
  assert.equal(await page.locator('#translationOriginal').textContent(),original);
  await page.locator('#language').evaluate(el=>el.click());
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
  await page.screenshot({path:path.join(out,'translation-preview-mobile.png'),fullPage:false,animations:'disabled'});
  await page.setViewportSize({width:1440,height:1080});
  await page.screenshot({path:path.join(out,'translation-preview.png'),fullPage:false,animations:'disabled'});
  assert.equal(writes.length,0);
  await page.locator('#translationCancel').click();
  translationFail=true;
  await page.locator('#translateBtn').click();
  await page.waitForFunction(()=>!document.querySelector('#translateBtn').disabled);
  assert.equal(await page.locator('#fb').inputValue(),original);
  assert((await page.locator('#toast').textContent()).includes('翻译暂时失败'));
  translationFail=false;translationDelay=400;
  await page.locator('#translateBtn').click();
  await page.locator('#fb').fill('翻译期间新写的评语');
  await page.waitForSelector('#translationDialog.on');
  await page.locator('#translationUse').click();
  assert.equal(await page.locator('#fb').inputValue(),'翻译期间新写的评语');
  assert((await page.locator('#translationError').textContent()).includes('总评已修改'));
  await page.locator('#translationCancel').click();
  translationDelay=0;
  await page.locator('#fb').fill(original);
  await page.locator('#translateBtn').click();
  await page.waitForSelector('#translationDialog.on');
  await page.locator('#translationUse').click();
  assert.equal(await page.locator('#fb').inputValue(),'A completed the task, but B did not.');
  assert.equal(writes.length,0);
  await page.locator('#restoreTranslation').click();
  assert.equal(await page.locator('#fb').inputValue(),original);
  await page.reload({waitUntil:'networkidle'});
  await page.waitForSelector('#restoreTranslation:visible');
  await page.locator('#restoreTranslation').click();
  assert.equal(await page.locator('#fb').inputValue(),original);
  assert.equal(translationCalls.length,4);
  assert(translationCalls.every(x=>x.text===original));
  await page.locator('[data-review-side="A"]').click();await page.locator('#sc-A').fill('100');await page.locator('[data-review-side="B"]').click();await page.locator('#sc-B').fill('50');
  await page.locator('[data-pref="A"]').click();
  await page.locator('#fb').fill('A 完成了任务，B 没完成。');
  await page.locator('#saveBtn').click();
  await page.waitForFunction(()=>document.querySelector('#toast').classList.contains('on'));
  assert.deepEqual(writes[0],{action:'save',preference:'A',feedback:'A 完成了任务，B 没完成。',score_A:'100',score_B:'50'});
  await page.waitForLoadState('networkidle');
  await page.evaluate(async()=>{CFG.feedback_generation_enabled=true;await loadDetail('offline_feedback_fixture')});
  assert.equal(await page.locator('#genBtn').count(),1);
  await page.evaluate(async()=>{CFG.feedback_generation_enabled=false;await loadDetail('offline_feedback_fixture')});
  assert.equal(await page.locator('#genBtn').count(),0);
  await page.locator('#discardBtn').click();
  await page.locator('#discardConfirm').click();
  assert.equal(writes.length,1);assert(await page.locator('#discardError').textContent());
  await page.locator('#discardReason').fill('Offline browser test only');
  await page.screenshot({path:path.join(out,'feedback-discard-fixture.png'),fullPage:true});
  await page.locator('#discardConfirm').click();
  await page.waitForFunction(()=>!document.querySelector('#discardDialog').classList.contains('on'));
  assert.equal(writes.length,2);assert.equal(writes[1].reason,'Offline browser test only');
  await page.locator('#technicalLogs summary').click();
  await page.waitForFunction(()=>document.querySelector('#policyLog').textContent.includes('Policy fixture log'));
  await page.locator('#language').click();
  assert((await page.locator('#policyLog').textContent()).includes('Policy fixture log'));
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
  assert.deepEqual(errors,[]);assert.deepEqual(dialogs,[]);
  const result={passed:true,fixture:true,real_router_writes:0,models:true,roster:'T0-T9',seek_and_end:true,
   discard_modal:true,client_policy_logs:true,translation_preview_restore_failure_and_race:true,errors};
  fs.writeFileSync(path.join(out,'feedback-browser.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
