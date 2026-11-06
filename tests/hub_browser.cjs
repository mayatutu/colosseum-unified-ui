// Two real loopback HTTP/WS servers with simulated Clients. Never connects to the lab.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('assert'),fs=require('fs'),path=require('path');
(async()=>{
 await Promise.all([8870,8871].map(port=>fetch('http://127.0.0.1:'+port+'/test/reset',{method:'POST'})));
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8870/',{waitUntil:'networkidle'});
  await page.waitForSelector('#frames iframe');
  const localId=await page.locator('#robotPicker').inputValue();
  let yam=page.frames().find(f=>f.url().includes('/s/'+localId+'/'));
  await yam.waitForFunction(()=>typeof ST!=='undefined'&&ST!==null);
  await yam.locator('[data-v="record"]').click();
  await yam.locator('#instruction').fill('YAM task one');await yam.locator('#evaluator').selectOption('T0');
  // Add a remote station via the real registry and identity probe.
  await page.locator('#addRobot').click();await page.locator('#robotName').fill('Franka test');
  await page.locator('#robotAddress').fill('127.0.0.1:8871');await page.locator('#robotSave').click();
  await page.waitForFunction(()=>document.querySelectorAll('#frames iframe').length===2);
  const remoteId=await page.locator('#robotPicker').inputValue();assert.notEqual(remoteId,localId);
  let franka=page.frames().find(f=>f.url().includes('/s/'+remoteId+'/'));
  await franka.waitForFunction(()=>typeof ST!=='undefined'&&ST!==null);
  assert.equal(await franka.evaluate(()=>CFG.robot),'franka');
  await franka.locator('[data-v="record"]').click();await franka.locator('#instruction').fill('Franka task two');
  await franka.locator('#evaluator').selectOption('T0');
  await page.locator('#robotPicker').selectOption(localId);
  assert.equal(await yam.locator('#instruction').inputValue(),'YAM task one');
  await yam.locator('#start').click();await yam.waitForFunction(()=>ST.recording===true);
  await page.locator('#robotPicker').selectOption(remoteId);
  assert.equal(await franka.locator('#instruction').inputValue(),'Franka task two');
  await franka.locator('#start').click();await franka.waitForFunction(()=>ST.recording===true);
  const events=async(port)=>fetch('http://127.0.0.1:'+port+'/test/events').then(r=>r.json());
  let y=await events(8870),f=await events(8871);
  assert(y.recording&&f.recording,'Both fake stations should keep running');
  assert.equal(y.calls.filter(c=>c[0]==='start').at(-1)[1].instruction,'YAM task one');
  assert.equal(f.calls.filter(c=>c[0]==='start').at(-1)[1].instruction,'Franka task two');
  assert(!y.calls.some(c=>c[0]==='finish'));assert(!f.calls.some(c=>c[0]==='finish'));
  // Same evaluation id on both stations must not share drafts, preferences, or video URLs.
  await franka.locator('[data-v="review"]').click();await franka.locator('#fb').fill('Franka private draft');
  await franka.locator('#sc-A').fill('65');await franka.locator('[data-pref="B"]').click();
  assert((await franka.locator('video').first().getAttribute('src')).startsWith('/s/'+remoteId+'/video/'));
  await page.locator('#robotPicker').selectOption(localId);await yam.locator('[data-v="review"]').click();
  assert.equal(await yam.locator('#fb').inputValue(),'');await yam.locator('#fb').fill('YAM independent draft');
  await yam.locator('#sc-A').fill('90');await yam.locator('[data-pref="A"]').click();
  await page.locator('#robotPicker').selectOption(remoteId);
  assert.equal(await franka.locator('#fb').inputValue(),'Franka private draft');
  assert.equal(await franka.locator('#sc-A').inputValue(),'65');
  await franka.locator('#saveBtn').click();await franka.waitForFunction(()=>document.querySelector('#toast').classList.contains('on'));
  y=await events(8870);f=await events(8871);
  assert.equal(y.calls.filter(c=>c[0]==='act').length,0);
  assert.equal(f.calls.filter(c=>c[0]==='act').at(-1)[1].body.feedback,'Franka private draft');
  // Fetch a byte range through the gateway; use the existing synthetic video file.
  const range=await page.request.get('http://127.0.0.1:8870/s/'+remoteId+'/video/same_record_id/run_A/head_image',{headers:{Range:'bytes=0-15'}});
  assert.equal(range.status(),206);assert.equal((await range.body()).length,16);
  await page.locator('#allStats').click();await page.waitForFunction(()=>document.querySelectorAll('#hubStatsRows tr').length===2);
  await page.locator('#allStatsClose').click();
  await page.locator('#language').click();assert.equal(await page.locator('html').getAttribute('lang'),'en');
  await franka.waitForFunction(()=>document.documentElement.lang==='en');
  await page.locator('#language').click();
  await page.screenshot({path:path.resolve(__dirname,'../validation/hub-two-stations.png'),fullPage:true});
  // Missing target can be registered without launching anything, and cannot fall back to YAM.
  await page.locator('#addRobot').click();await page.locator('#robotName').fill('Offline fixture');
  await page.locator('#robotAddress').fill('127.0.0.1:8899');await page.locator('#robotSave').click();
  await page.waitForSelector('#offlinePanel:not([hidden])');assert.equal(await page.locator('#frames iframe').count(),2);
  await page.locator('#allStats').click();await page.waitForFunction(()=>document.querySelector('#hubStatsNotice').textContent.includes('Offline fixture'));
  await page.locator('#allStatsClose').click();await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
  await page.screenshot({path:path.resolve(__dirname,'../validation/hub-mobile.png'),fullPage:true});
  await page.locator('#robotPicker').selectOption(localId);
  await page.reload({waitUntil:'networkidle'});
  yam=page.frames().find(f=>f.url().includes('/s/'+localId+'/'));
  await yam.waitForFunction(()=>typeof ST!=='undefined'&&ST!==null);await yam.locator('[data-v="review"]').click();
  assert.equal(await yam.locator('#fb').inputValue(),'YAM independent draft');
  y=await events(8870);f=await events(8871);assert(y.recording&&f.recording);
  assert.deepEqual(errors,[]);
  const result={passed:true,simulated_stations:2,concurrent:true,http_and_websocket:true,range:true,
    isolated_drafts_and_actions:true,offline_registry:true,hardware:false,router_isolation_verified:false,errors};
  fs.writeFileSync(path.resolve(__dirname,'../validation/hub-browser.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
