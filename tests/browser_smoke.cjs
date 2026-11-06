// Actual candidate UI on localhost, empty real storage; no fake Router or eval records.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const path=require('path'),fs=require('fs'),assert=require('assert');
(async()=>{
 const out=path.resolve(__dirname,'../validation');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined,args:['--disable-background-networking']});
 const page=await browser.newPage({viewport:{width:1440,height:1050}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8870/',{waitUntil:'networkidle'});
 await page.waitForFunction(()=>typeof ST!=='undefined'&&ST!==null);
 assert.equal(await page.locator('html').getAttribute('lang'),'zh-CN');
 await page.screenshot({path:path.join(out,'setup-zh.png'),fullPage:true});
 await page.locator('[data-a="__keys"]').click();
 assert.equal(await page.locator('#keyInputs').evaluate(e=>e.disabled),true);
 assert.equal(await page.locator('#keysSave').isDisabled(),true);
 await page.locator('#keysUnlock').click();
 assert.equal(await page.locator('#keyInputs').evaluate(e=>e.disabled),false);
 await page.screenshot({path:path.join(out,'settings-unlocked-zh.png')});
 await page.locator('#keysCancel').click();
 await page.locator('[data-a="__keys"]').click();
 assert.equal(await page.locator('#keyInputs').evaluate(e=>e.disabled),true);
 await page.locator('#keysCancel').click();
 await page.locator('[data-v="record"]').click();
 await page.locator('#instruction').fill('用户输入 Setup must remain unchanged');
 await page.screenshot({path:path.join(out,'record-zh.png'),fullPage:true});
 await page.locator('#language').click();
 assert.equal(await page.locator('html').getAttribute('lang'),'en');
 assert.equal(await page.locator('#instruction').inputValue(),'用户输入 Setup must remain unchanged');
 await page.screenshot({path:path.join(out,'record-en.png'),fullPage:true});
 await page.locator('#language').click();
 await page.locator('[data-v="review"]').click();
 await page.waitForTimeout(250);
 await page.screenshot({path:path.join(out,'review-zh.png'),fullPage:true});
 await page.locator('[data-v="stats"]').click();
 await page.waitForFunction(()=>document.querySelector('#statsRows').textContent.length>0);
 await page.screenshot({path:path.join(out,'stats-zh.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:path.join(out,'stats-mobile-zh.png'),fullPage:true});
 const horizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);
 assert.equal(horizontalOverflow,false,'mobile horizontal overflow');
 // Browser-only review form fixture. Never written to real storage or sent to a Router.
 const submissions=[];
 const fixture={id:'ui_test_fixture',instruction:'UI test fixture — not a real evaluation',scene:'test only',
  state:'review',time:1700000000,busy:false,managed:false,preference:'',feedback:'',factors:{},log:'',
  runs:['A','B'].map(side=>({id:'test_'+side,side,recorded:false,cams:[],stop:null,notes:'',score:null}))};
 await page.route('**/api/evals**',async route=>{
  const req=route.request(),url=new URL(req.url());
  if(req.method()==='POST'){submissions.push(req.postDataJSON());return route.fulfill({json:{msg:'Draft saved.'}})}
  return route.fulfill({json:url.pathname==='/api/evals'?
   (url.searchParams.has('paginated')?{items:[fixture],total:1,offset:0,limit:100}:[fixture]):fixture});
 });
 await page.setViewportSize({width:1440,height:1100});
 await page.locator('[data-v="review"]').click();
 await page.locator('#sc-A').fill('100');await page.locator('#sc-B').fill('50');
 await page.locator('#fb').fill('总评内容 Setup 不应被翻译');
 await page.locator('[data-pref="A"]').click();
 await page.locator('#language').click();
 assert.equal(await page.locator('#fb').inputValue(),'总评内容 Setup 不应被翻译');
 assert.equal(await page.locator('#sc-A').inputValue(),'100');
 await page.locator('#language').click();
 await page.evaluate(()=>window.scrollTo(0,0));
 await page.screenshot({path:path.join(out,'test-fixture-review-zh.png'),fullPage:true});
 await page.locator('#saveBtn').click();
 await page.waitForFunction(()=>document.querySelector('#toast').classList.contains('on'));
 assert.equal(submissions[0].score_A,'100');assert.equal(submissions[0].preference,'A');
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'browser-smoke.json'),JSON.stringify({passed:true,errors,screenshots:8,backend:'actual candidate with empty local storage; review form uses a browser-only fixture',hardware:false,router:false},null,2));
 await browser.close();console.log('Browser checks passed. Actual empty UI; no hardware or Router mutation.');
})().catch(e=>{console.error(e);process.exit(1)});
