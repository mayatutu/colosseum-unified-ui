// Read-only deployment smoke: never enter Record or invoke checks/maintenance.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('assert'),fs=require('fs'),path=require('path');
(async()=>{
 const out=path.resolve(__dirname,'../validation');
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined,args:['--disable-background-networking']});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1050}});
  const errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()!=='GET')writes.push(r.method()+' '+r.url())});
  await page.goto('http://yam-client.example.invalid:8772/station',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>typeof ST!=='undefined'&&ST!==null);
  assert.equal(await page.evaluate(()=>CFG.station),'yam');
  assert.equal(await page.evaluate(()=>CFG.feedback_generation_enabled),false);
  assert.equal(await page.evaluate(()=>ST.recording),false);
  assert.equal(await page.evaluate(()=>ST.preview),false);
  assert.equal(await page.locator('#evaluator').evaluate(e=>e.tagName),'SELECT');
  assert.deepEqual(await page.locator('#evaluator option').evaluateAll(es=>es.map(e=>e.value).filter(Boolean)),Array.from({length:10},(_,i)=>'T'+i));
  await page.evaluate(()=>openDiscard('ev_example'));
  assert(await page.locator('#discardDialog').evaluate(e=>e.classList.contains('on')));
  await page.locator('#discardCancel').click();
  assert.equal(await page.locator('#discardDialog').evaluate(e=>e.classList.contains('on')),false);
  await page.screenshot({path:path.join(out,'yam-deployed-setup.png'),fullPage:true});
  await page.locator('[data-a="__keys"]').click();
  assert(await page.locator('#keyInputs').evaluate(e=>e.disabled));
  await page.locator('#keysUnlock').click();
  assert.equal(await page.locator('#keyInputs').evaluate(e=>e.disabled),false);
  await page.locator('#keysCancel').click();
  await page.locator('#language').click();
  assert.equal(await page.locator('html').getAttribute('lang'),'en');
  await page.locator('#language').click();
  await page.locator('[data-v="stats"]').click();
  await page.waitForFunction(()=>document.querySelector('#statsRows').textContent.length>0);
  await page.screenshot({path:path.join(out,'yam-deployed-stats.png'),fullPage:true});
  // Inspect the real review form without requesting video generation or writing records.
  await page.route('**/video/**',route=>route.abort());
  await page.locator('[data-v="review"]').click();
  await page.waitForFunction(()=>document.querySelector('#evlist').textContent.trim().length>0);
  if(await page.locator('#evlist .evitem').count()===0)await page.locator('[data-filter="all"]').click();
  await page.waitForSelector('#fb');
  assert.equal(await page.locator('#fb').getAttribute('aria-required'),'true');
  if(await page.locator('#translateBtn').count())assert.equal(await page.locator('#translateBtn').textContent(),'翻译');
  else assert(await page.locator('#fb').isDisabled());
  assert.equal(await page.locator('#translationDialog').count(),1);
  assert(await page.locator('#evdetail').innerText().then(t=>t.includes('必填')));
  assert.equal(await page.locator('#ob-A,#ob-B,[data-f],#genBtn').count(),0);
  assert.equal(await page.locator('#evdetail textarea').count(),1);
  assert.equal(await page.locator('#sc-A,#sc-B').count(),2);
  assert.equal(await page.locator('[data-pref]').count(),3);
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  const result={passed:true,url:page.url(),errors,writes,hardware:false,router_submission:false};
  fs.writeFileSync(path.join(out,'yam-deployment-browser.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
