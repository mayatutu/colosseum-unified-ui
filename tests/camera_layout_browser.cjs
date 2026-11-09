const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const out=path.resolve(__dirname,'../validation');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE});
 const results=[];
 try{
  for(const [robot,port] of [['yam',Number(process.env.HUB_TEST_PORT||8870)],['franka',Number(process.env.REMOTE_TEST_PORT||8871)]]){
   const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1.5}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/api/evals/same_record_id',async route=>{
    if(route.request().method()!=='GET')return route.continue();
    const response=await route.fetch(),data=await response.json();
    for(const run of data.runs){run.cams=['head_image','left_image','right_image'];run.stop={reason:'done',step:202};}
    return route.fulfill({json:data});
   });
   await page.goto('http://127.0.0.1:'+port+'/#review');
   await page.waitForFunction(()=>document.querySelector('#frames iframe')?.contentWindow.location.pathname.startsWith('/s/'));
   const frame=page.frames().find(f=>f.url().includes('/s/'));
   await frame.waitForSelector('#reviewPlayer');
   await frame.waitForFunction(()=>document.querySelector('.review-cameras').style.height);
   const sizes=[];
   for(const viewport of [{width:1440,height:1000},{width:1280,height:720},{width:1152,height:520},{width:1000,height:600},{width:800,height:450},{width:1920,height:1080},{width:768,height:900},{width:390,height:844},{width:320,height:568}]){
    await page.setViewportSize(viewport);await page.waitForTimeout(200);
    for(const side of ['A','B']){
     await frame.locator(`[data-review-side="${side}"]`).click();
     await frame.locator('#reviewPlayer').evaluate(e=>e.scrollIntoView({block:'start'}));
     await page.waitForTimeout(200);
     const panel=frame.locator(`[data-review-panel="${side}"]`);
     const boxes=await Promise.all([0,1,2].map(i=>panel.locator('video').nth(i).boundingBox()));
     const seek=await frame.locator(`[data-seek="${side}"]`).boundingBox();
     const play=await frame.locator(`[data-play="${side}"]`).boundingBox();
     for(const box of [...boxes,seek,play])assert.ok(box&&box.y>=-1&&box.y+box.height<=viewport.height+1,JSON.stringify({robot,viewport,side,boxes,seek,play}));
     assert.equal(await panel.locator('video').count(),3);
     assert.equal(await frame.locator('.side:not([hidden])').count(),1);
     if(await panel.locator('.review-cameras').getAttribute('data-layout')==='side'){assert.ok(boxes[0].x<boxes[1].x);assert.ok(boxes[0].height>boxes[1].height*1.9);assert.ok(boxes[2].y>=boxes[1].y+boxes[1].height)}
     else {assert.ok(boxes[1].y>=boxes[0].y+boxes[0].height);assert.ok(Math.abs(boxes[1].y-boxes[2].y)<2)}
     assert.equal(await panel.locator('video').first().evaluate(e=>getComputedStyle(e).objectFit),'contain');
     const dimensions=await panel.locator('video').evaluateAll(videos=>videos.map(v=>{
      const b=v.getBoundingClientRect(),ratio=v.videoWidth/v.videoHeight,w=Math.min(b.width,b.height*ratio);
      return {fill:w*w/ratio/(b.width*b.height),height:b.height,filter:getComputedStyle(v).filter};
     }));
     for(const d of dimensions){assert.ok(d.fill>.97,JSON.stringify({viewport,side,d}));assert.equal(d.filter,'none')}
     assert.ok(dimensions[0].height>Math.min(viewport.height*.45,(viewport.width-66)*.65));
     const score=await frame.locator('#sc-'+side).boundingBox();assert.ok(score.y>=0&&score.y+score.height<=viewport.height+1);
     assert.ok(await panel.evaluate(p=>[...p.querySelectorAll('*')].every(e=>e.getBoundingClientRect().right<=innerWidth+1)));
     assert.equal(await panel.locator('.chip').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(180, 83, 42)');
    }
    const first=await frame.locator('#reviewPlayer').evaluate(e=>e.getBoundingClientRect().height);
    await page.waitForTimeout(250);const second=await frame.locator('#reviewPlayer').evaluate(e=>e.getBoundingClientRect().height);
    assert.ok(Math.abs(first-second)<2);assert.ok(second<=viewport.height);
    sizes.push({...viewport,playerHeight:second,all_three_visible:true});
    if(viewport.width===1440||viewport.width===390)await page.screenshot({path:path.join(out,robot+'-'+viewport.width+'.png')});
   }
   await page.setViewportSize({width:1440,height:1000});
   await frame.locator('[data-review-side="A"]').click();await frame.locator('#sc-A').fill('90');
   await frame.locator('[data-play="A"]').click();
   await frame.waitForFunction(()=>document.querySelector('video[data-side=A]').currentTime>.2);
   await frame.locator('[data-review-side="B"]').click();await frame.locator('#sc-B').fill('60');
   assert.equal(await frame.locator('video[data-side=A]').evaluateAll(v=>v.every(x=>x.paused)),true);
   await frame.locator('[data-review-side="A"]').click();assert.equal(await frame.locator('#sc-A').inputValue(),'90');
   await frame.locator('#fb').fill('Offline camera layout validation');await frame.locator('[data-pref=A]').click();
   await frame.locator('#saveBtn').click();
   const events=await (await page.request.get('http://127.0.0.1:'+port+'/test/events')).json();
   const save=events.calls.filter(x=>x[0]==='act').at(-1)[1].body;
   assert.equal(save.score_A,'90');assert.equal(save.score_B,'60');
   assert.ok(!events.calls.some(x=>['start','finish','maintenance'].includes(x[0])));
   assert.deepEqual(errors,[]);
   results.push({robot,sizes,tab_switch_pauses_only_playback:true,both_scores_preserved:true,errors});
   await page.close();
  }
  fs.writeFileSync(path.join(out,'camera-checks.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
