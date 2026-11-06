const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_EXECUTABLE||undefined,headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],posts=[],listCalls=[];
  page.on('pageerror',e=>errors.push(e.message));
  const state=await (await page.request.get('http://127.0.0.1:18873/api/state')).json();
  let socket;
  await page.routeWebSocket('**/ws',ws=>{socket=ws;ws.send(JSON.stringify(state))});
  const items=Array.from({length:1770},(_,i)=>({id:'ev_'+i,instruction:'Task '+i,scene:'Test',state:i<1456?'submitted':i<1464?'discarded':'interrupted',time:1700000000-i,busy:false}));
  await page.route('**/api/evals**',async route=>{
   const url=new URL(route.request().url()),id=url.pathname.split('/').pop();
   if(id==='evals'){
    listCalls.push(url.search);const offset=+url.searchParams.get('offset'),limit=+url.searchParams.get('limit');
    return route.fulfill({json:{items:items.slice(offset,offset+limit),offset,limit,total:items.length}});
   }
   const n=+id.split('_')[1];if(n===1)await new Promise(r=>setTimeout(r,250));
   return route.fulfill({json:{...items[n],preference:'A',feedback:'test',factors:{},log:'',
    runs:['A','B'].map(side=>({id:'run_'+side,side,recorded:true,cams:['head_image'],score:100,stop:null,model_name:side}))}});
  });
  await page.route('**/api/eval/finish',route=>{posts.push(route.request().postDataJSON());return route.fulfill({json:{ok:true}})});
  await page.addInitScript(()=>localStorage.setItem('evfilter:local','submitted'));
  await page.goto('http://127.0.0.1:18873/station#review');
  await page.waitForFunction(()=>document.querySelectorAll('#evlist .evitem').length===100&&document.querySelectorAll('#evdetail video').length===2);
  assert.equal(listCalls.length,1);
  assert.ok((await page.locator('#filters').innerText()).includes('1770'));
  await page.evaluate(()=>window.firstPlayer=document.querySelector('#evdetail video'));
  const t=Date.now();await page.locator('[data-filter="all"]').click();
  assert.equal(await page.evaluate(()=>window.firstPlayer===document.querySelector('#evdetail video')),true);
  await page.locator('[data-filter="todo"]').click();assert.equal(await page.locator('#evdetail video').count(),0);
  await page.locator('[data-filter="submitted"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('#evdetail video').length===2);
  assert.equal(listCalls.length,1);
  await page.locator('[data-id="ev_1"]').click();await page.locator('[data-id="ev_2"]').click();
  await page.waitForTimeout(350);
  assert.ok((await page.locator('#evdetail').innerText()).includes('Task 2'));
  assert.ok(!(await page.locator('#evdetail').innerText()).includes('Task 1\n'));
  const beforeMore=listCalls.length;
  await page.locator('#moreEvals').click();assert.equal(await page.locator('#evlist .evitem').count(),200);assert.equal(listCalls.length,beforeMore);
  const filterMs=Date.now()-t;
  await page.screenshot({path:require('path').resolve(__dirname,'../validation/review-1770-browser.png'),fullPage:true});
  await page.evaluate(()=>{show('record',false);document.querySelector('#instruction').value='Old task';document.querySelector('#scene').value='Old scene'});
  socket.send(JSON.stringify({...state,recording:true,run:{...state.run,phase:'running',eval_id:'ev_old',instruction:'Old task'}}));
  await page.locator('#killBtn').click();assert.equal(posts[0].reason,'stopped');assert.equal(posts[0].expected_eid,'ev_old');
  socket.send(JSON.stringify({...state,recording:true,run:{...state.run,phase:'stopping',eval_id:'ev_old'}}));
  await page.waitForTimeout(50);assert.equal(await page.locator('#rec-form').isVisible(),false);
  socket.send(JSON.stringify({...state,run:{...state.run,phase:'idle',eval_id:null,restarted_from:'ev_old'}}));
  await page.waitForFunction(()=>document.querySelector('#instruction').value==='');
  assert.equal(await page.locator('#scene').inputValue(),'');assert.equal(await page.locator('#resume').inputValue(),'');
  await page.locator('#instruction').fill('New draft');socket.send(JSON.stringify({...state,run:{...state.run,phase:'idle',eval_id:null,restarted_from:'ev_old'}}));
  await page.waitForTimeout(50);assert.equal(await page.locator('#instruction').inputValue(),'New draft');
  socket.send(JSON.stringify({...state,recording:true,run:{...state.run,phase:'running',eval_id:'ev_new'}}));
  await page.locator('#doneBtn').click();assert.equal(posts[1].reason,'completed');
  const config=await (await page.request.get('http://127.0.0.1:18873/test/config')).json();
  assert.ok(!config.calls.some(([m])=>m==='start'||m==='preview'));
  assert.deepEqual(errors,[]);
  const result={passed:true,records:1770,initial_list_requests:1,filter_and_row_list_requests:0,render_batch:100,filter_test_ms:filterMs,stop_blank_form:true,completed_separate:true,no_real_devices:true};
  fs.writeFileSync(require('path').resolve(__dirname,'../validation/review_stop_browser-results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
