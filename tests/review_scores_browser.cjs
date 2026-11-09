// Loopback fixtures only: never change a real evaluation or submit to a Router.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE});
 const results=[];
 try{
  for(const [robot,port] of [['yam',Number(process.env.HUB_TEST_PORT||8870)],['franka',Number(process.env.REMOTE_TEST_PORT||8871)]]){
   const base='http://127.0.0.1:'+port;
   const page=await browser.newPage({viewport:{width:1280,height:720}}),errors=[],scripts=[];
   await page.request.post(base+'/test/reset');
   page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>localStorage.setItem('station-language','zh-CN'));
   // Model the old unversioned script remaining cached during a static update.
   await page.route('**/station.js*',async route=>{
    const url=new URL(route.request().url());scripts.push(url.pathname+url.search);
    if(url.searchParams.get('v'))return route.continue();
    const response=await route.fetch();
    const old=(await response.text()).split('let reviewLayoutCleanup=')[0];
    return route.fulfill({response,body:old});
   });
   const review=async()=>{
    await page.goto(base+'/#review');
    await page.waitForFunction(()=>document.querySelector('#frames iframe')?.contentWindow.location.pathname.startsWith('/s/'));
    const frame=page.frames().find(f=>f.url().includes('/s/'));
    await frame.waitForSelector('#reviewPlayer');return frame;
   };
   let frame=await review();
   const values={};
   for(const side of ['A','B']){
    await frame.locator(`[data-review-side="${side}"]`).click();
    const range=frame.locator('#rg-'+side),number=frame.locator('#sc-'+side);
    await range.scrollIntoViewIfNeeded();const box=await range.boundingBox();
    await page.mouse.move(box.x+8,box.y+box.height/2);await page.mouse.down();
    await page.mouse.move(box.x+box.width*(side==='A'?.4:.6),box.y+box.height/2,{steps:12});await page.mouse.up();
    assert.equal(await number.inputValue(),await range.inputValue());assert.ok(Number(await number.inputValue())>0);
    await number.fill('90');assert.equal(await range.inputValue(),'90');
    await range.focus();await range.press('Home');assert.equal(await number.inputValue(),'0');
    await range.press('End');assert.equal(await number.inputValue(),'100');
    for(let i=0;i<(side==='A'?3:8);i++)await range.press('ArrowLeft');
    values[side]=await number.inputValue();assert.equal(values[side],side==='A'?'85':'60');
   }
   // Local draft must preserve both scores even though only one tab is visible.
   frame=await review();
   for(const side of ['A','B']){
    await frame.locator(`[data-review-side="${side}"]`).click();
    assert.equal(await frame.locator('#sc-'+side).inputValue(),values[side]);
    assert.equal(await frame.locator('#rg-'+side).inputValue(),values[side]);
   }
   await frame.locator('#fb').fill('Offline slider regression');await frame.locator('[data-pref=A]').click();
   const saved=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/api/evals/same_record_id'));
   await frame.locator('#saveBtn').click();assert.equal((await saved).status(),200);
   const events=await (await page.request.get(base+'/test/events')).json();
   const body=events.calls.filter(x=>x[0]==='act').at(-1)[1].body;
   assert.equal(body.action,'save');assert.equal(body.score_A,'85');assert.equal(body.score_B,'60');
   assert.ok(!events.calls.some(x=>['start','finish','maintenance'].includes(x[0])));
   frame=await review();
   for(const side of ['A','B'])assert.equal(await frame.locator('#sc-'+side).inputValue(),values[side]);
   assert.ok(scripts.length>0&&scripts.every(url=>new URL(url,base).searchParams.get('v')));
   assert.deepEqual(errors,[]);
   results.push({robot,mouse_drag:true,number_sync:true,keyboard_bounds:true,both_tab_drafts:true,saved_and_reloaded:true,versioned_scripts:true});
   await page.close();
  }
  console.log(JSON.stringify(results));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
