// Offline UI checks: all HTTP/WebSocket traffic is intercepted; no devices or translation provider.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(process.env.UI_ROOT||path.join(__dirname,'..'));
const out=path.resolve(process.env.TASK_TRANSLATION_OUTPUT||path.join(root,'validation/task-translation'));
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 const results=[];
 try{
  for(const robot of ['franka','yam']){
   const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[],writes=[];
   const prefix='/s/'+robot+'-fixture';let fail=false,hold=null,release=null;
   const state={checks:Object.fromEntries(['gpu','can','arms','cameras','router','keys','server'].map(k=>[k,{status:'ok',detail:''}])),
    run:{phase:'idle',side:null,step:0,max_steps:800,eval_id:null,instruction:'',message:''},
    log:[],prompt:null,preview:false,recording:false,pending:[],models:{},keys:[],thumbs:[]};
   const detail={id:'feedback-fixture',instruction:'Test task',scene:'test',state:'review',managed:true,busy:false,time:1,
    feedback:'',preference:'',factors:{},runs:['A','B'].map(side=>({side,id:side,recorded:false,cams:[],score:null}))};
   page.on('pageerror',e=>errors.push(e.message));
   await page.routeWebSocket('**/ws',ws=>ws.send(JSON.stringify(state)));
   await page.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.hostname!=='127.0.0.1')return route.abort();
    const routePath=url.pathname.startsWith(prefix)?url.pathname.slice(prefix.length):url.pathname;
    if(request.method()==='POST'){
     writes.push({path:url.pathname,body:request.postDataJSON()});
     if(routePath==='/api/translate'){
      if(hold)await hold;
      return route.fulfill({status:fail?502:200,json:fail?{detail:'Translation failed. Your original comment is unchanged.'}:{text:'Put the red cup on the plate.'}});
     }
     if(routePath.startsWith('/api/preview/'))return route.fulfill({json:{ok:true}});
     throw Error('Unexpected control/write request: '+url.pathname);
    }
    const file={'/':'eval_gui.html','/station.js':'station.js','/i18n.js':'i18n.js'}[routePath];
    if(file)return route.fulfill({contentType:file.endsWith('.html')?'text/html':'text/javascript',body:fs.readFileSync(path.join(root,file))});
    let data={};
    if(routePath==='/api/config')data={robot,station:robot,institution:'OFFLINE',people:[],evaluator_options:['T0'],maintenance:[],max_steps:800,settings_mode:'keys'};
    else if(routePath==='/api/state')data=state;
    else if(routePath==='/api/evals')data={items:[detail],total:1};
    else if(routePath==='/api/evals/feedback-fixture')data=detail;
    else if(routePath==='/api/stats')data={rows:[]};
    return route.fulfill({json:data});
   });
   const url='http://127.0.0.1:18879'+prefix+'/#record';
   await page.goto(url);await page.waitForFunction(()=>typeof ST!=='undefined'&&ST!==null);
   const input=page.locator('#instruction'),button=page.locator('#translateTaskBtn');
   const calls=()=>writes.filter(x=>x.path.endsWith('/api/translate'));
   await input.fill('  ');await button.click();assert.equal(calls().length,0);
   assert.match(await page.locator('#toast').textContent(),/请先填写任务/);
   const original='把红色杯子放到盘子上。';await input.fill(original);await button.click();
   await page.waitForSelector('#translationDialog.on');
   assert.equal(await input.inputValue(),original);
   assert.equal(await page.locator('#translationOriginal').textContent(),original);
   assert.equal(await page.locator('#translationOriginalLabel').textContent(),'翻译前任务');
   await page.locator('#translationCancel').click();assert.equal(await input.inputValue(),original);
   fail=true;await button.click();await page.waitForFunction(()=>!document.querySelector('#translateTaskBtn').disabled);
   assert.equal(await input.inputValue(),original);assert.match(await page.locator('#toast').textContent(),/原任务保持不变/);fail=false;
   hold=new Promise(resolve=>release=resolve);await button.click();await input.fill('新的任务');release();hold=null;
   await page.waitForSelector('#translationDialog.on');await page.locator('#translationUse').click();
   assert.equal(await input.inputValue(),'新的任务');assert.match(await page.locator('#translationError').textContent(),/任务已修改/);
   await page.locator('#translationCancel').click();
   await input.fill(original);await button.click();await page.waitForSelector('#translationDialog.on');
   await page.locator('#translationResult').fill('  ');await page.locator('#translationUse').click();
   assert.equal(await input.inputValue(),original);assert.match(await page.locator('#translationError').textContent(),/译文不能为空/);
   await page.locator('#translationResult').fill('Place the red cup onto the plate.');await page.locator('#translationUse').click();
   assert.equal(await input.inputValue(),'Place the red cup onto the plate.');
   assert.equal(await page.evaluate(key=>JSON.parse(sessionStorage.getItem('station-form:'+key)).instruction,prefix),'Place the red cup onto the plate.');
   await page.reload();await page.waitForSelector('#restoreTaskTranslation:visible');
   assert.equal(await input.inputValue(),'Place the red cup onto the plate.');
   await page.locator('#restoreTaskTranslation').click();assert.equal(await input.inputValue(),original);
   await button.click();await page.waitForSelector('#translationDialog.on');
   await page.screenshot({path:path.join(out,robot+'-task-translation.png')});
   await page.setViewportSize({width:390,height:844});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
   await page.screenshot({path:path.join(out,robot+'-task-translation-mobile.png')});
   await page.locator('#translationCancel').click();await page.setViewportSize({width:1280,height:900});
   // Existing feedback translation uses the same preview without sharing task originals.
   await page.evaluate(async()=>{show('review',false);await loadDetail('feedback-fixture')});
   await page.locator('#fb').fill('总评原文');await page.locator('#translateBtn').click();
   await page.waitForSelector('#translationDialog.on');assert.equal(await page.locator('#translationOriginalLabel').textContent(),'翻译前原文');
   await page.locator('#translationUse').click();await page.locator('#restoreTranslation').click();
   assert.equal(await page.locator('#fb').inputValue(),'总评原文');assert.equal(await input.inputValue(),original);
   await page.evaluate(()=>show('record',false));
   // Clearing a failed round also clears the task's restore state and invalidates an in-flight translation.
   hold=new Promise(resolve=>release=resolve);await button.click();await page.evaluate(()=>blankRoundForm('offline-round'));release();hold=null;
   await page.waitForFunction(()=>!document.querySelector('#translateTaskBtn').disabled);
   assert.equal(await input.inputValue(),'');assert.equal(await page.locator('#restoreTaskTranslation').isHidden(),true);
   assert.equal(await page.locator('#translationDialog').evaluate(el=>el.classList.contains('on')),false);
   assert.equal(await page.evaluate(key=>sessionStorage.getItem('colosseum-task-translation-original:'+key),prefix),null);
   assert(calls().every(x=>x.path===prefix+'/api/translate'));
   assert(writes.every(x=>x.path.endsWith('/api/translate')||x.path.includes('/api/preview/')));
   assert.deepEqual(errors,[]);results.push({robot,passed:true,translation_requests:calls().length,errors});await page.close();
  }
  fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
