const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_EXECUTABLE||undefined,headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],posts=[];
  let responseStatus=503;
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{window.nativeDialogCalls=0;window.confirm=()=>{window.nativeDialogCalls++;return false};localStorage.setItem('evfilter:local','todo')});
  await page.route('**/*',async route=>{
   const r=route.request(),url=new URL(r.url());
   if(r.method()!=='GET'){
    posts.push({url:r.url(),body:r.postDataJSON()});
    await new Promise(resolve=>setTimeout(resolve,150));
    return route.fulfill({status:responseStatus,json:responseStatus===200?{msg:'Mock submission accepted'}:{detail:'Injected Router unavailable'}});
   }
   if(url.pathname.includes('/video/'))return route.abort();
   return route.continue();
  });
  await page.goto('http://127.0.0.1:18874/#review');
  await page.waitForSelector('iframe');const frame=page.frames().find(f=>f.url().includes('/s/'));
  await frame.waitForFunction(()=>typeof ST!=='undefined'&&ST);
  await frame.evaluate(()=>show('review'));
  await frame.locator('#submitBtn').waitFor();
  await frame.locator('#taskDifficulty').fill('');await frame.locator('#submitBtn').click();
  assert.equal(await frame.locator('#submitDialog').isVisible(),false);assert.equal(posts.length,0);
  await frame.locator('#sc-A').fill('90');await frame.locator('#sc-B').fill('50');
  await frame.locator('[data-pref="A"]').click();await frame.locator('#taskDifficulty').fill('5');await frame.locator('#fb').fill('Test draft; never sent to Router.');
  await frame.locator('#submitBtn').click();assert.equal(await frame.locator('#submitDialog').isVisible(),true);
  assert.equal(await frame.evaluate(()=>window.nativeDialogCalls),0);assert.equal(posts.length,0);
  await frame.locator('#submitCancel').click();assert.equal(posts.length,0);
  await frame.locator('#submitBtn').click();await frame.locator('#submitCancel').press('Escape');assert.equal(await frame.locator('#submitDialog').isVisible(),false);
  await frame.locator('#submitBtn').click();
  await frame.locator('#submitConfirm').evaluate(b=>{b.click();b.click()});
  assert.equal(await frame.locator('#submitConfirm').isDisabled(),true);
  await frame.waitForFunction(()=>document.querySelector('#submitError').textContent.includes('Injected Router unavailable'));
  assert.equal(posts.length,1);assert.equal(await frame.locator('#fb').inputValue(),'Test draft; never sent to Router.');
  assert.equal(posts[0].body.action,'submit');assert.equal(posts[0].body.task_difficulty,'5');
  assert.equal(posts[0].body.score_A,'90');assert.equal(posts[0].body.score_B,'50');assert.equal(posts[0].body.preference,'A');
  await page.screenshot({path:require('path').resolve(__dirname,'../validation/submit-dialog-browser.png'),fullPage:true});
  await frame.locator('#submitCancel').click();responseStatus=200;
  await frame.locator('#submitBtn').click();await frame.locator('#submitConfirm').click();
  await frame.waitForFunction(()=>!document.querySelector('#submitDialog').classList.contains('on'));
  assert.equal(posts.length,2);assert.equal(await frame.evaluate(()=>window.nativeDialogCalls),0);assert.deepEqual(errors,[]);
  const result={passed:true,native_dialog_disabled:true,visible_confirmation:true,cancel_and_escape_no_submit:true,double_click_single_request:true,explicit_error:true,draft_preserved:true,success_closes_dialog:true,real_remote_writes:0};
  fs.writeFileSync(require('path').resolve(__dirname,'../validation/submit_dialog_browser-results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
