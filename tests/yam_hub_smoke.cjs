// Read-only live verification: no POST, no Record view, no remote service startup.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('assert'),fs=require('fs'),path=require('path');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),writes=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()!=='GET')writes.push(r.method()+' '+r.url())});
  await page.goto('http://yam-client.example.invalid:8772/',{waitUntil:'networkidle'});
  await page.waitForSelector('#frames iframe');
  const local=await page.locator('#robotPicker').inputValue();
  const yam=page.frames().find(f=>f.url().includes('/s/'+local+'/'));
  await yam.waitForFunction(()=>typeof ST!=='undefined'&&ST!==null);
  assert.equal(await yam.evaluate(()=>CFG.robot),'yam');
  assert.equal(await yam.evaluate(()=>ST.recording),false);
  assert.equal(await yam.evaluate(()=>ST.preview),false);
  const options=await page.locator('#robotPicker option').evaluateAll(es=>es.map(e=>({id:e.value,text:e.textContent})));
  const franka=options.find(o=>o.id!==local);assert(franka&&franka.text.includes('Franka'));
  await page.locator('#robotPicker').selectOption(franka.id);await page.waitForSelector('#offlinePanel:not([hidden])');
  assert.equal(await page.locator('#frames iframe').count(),1);
  await page.locator('#robotPicker').selectOption(local);
  await page.locator('#addRobot').click();assert(await page.locator('#robotName').isVisible());await page.locator('#robotCancel').click();
  await page.locator('#allStats').click();await page.waitForFunction(()=>document.querySelector('#hubStatsNotice').textContent.includes('Franka'));
  await page.locator('#allStatsClose').click();
  await page.screenshot({path:path.resolve(__dirname,'../validation/yam-hub-live.png'),fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  const result={passed:true,options,writes,errors,franka_offline:true,hardware:false};
  fs.writeFileSync(path.resolve(__dirname,'../validation/yam-hub-live.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
