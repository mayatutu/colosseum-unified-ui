// Full UI + loopback media server. Only fixture evaluations are opened.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),http=require('node:http'),assert=require('node:assert/strict');
const head=fs.readFileSync(process.env.HEAD_TEST_VIDEO),wrist=fs.readFileSync(process.env.WRIST_TEST_VIDEO);
let hold=true;
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost'),main=url.pathname==='/head.mp4',data=main?head:wrist;
 const range=/bytes=(\d+)-(\d*)/.exec(req.headers.range||''),start=range?+range[1]:0,end=range&&range[2]?Math.min(+range[2],data.length-1):data.length-1;
 res.writeHead(range?206:200,{'Content-Type':'video/mp4','Content-Length':end-start+1,'Accept-Ranges':'bytes','Cache-Control':'no-store',...(range?{'Content-Range':`bytes ${start}-${end}/${data.length}`}:{})});
 let position=start,timer;res.on('close',()=>clearTimeout(timer));
 function send(){
  if(res.destroyed)return;
  if(position>end){res.end();return}
  if(main&&hold&&position>=786432){timer=setTimeout(send,30);return}
  const next=Math.min(position+65536,end+1);res.write(data.subarray(position,next));position=next;timer=setTimeout(send,main?8:1);
 }send();
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const media='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE});
 const results=[];
 try{
  for(const [robot,port] of [['yam',Number(process.env.HUB_TEST_PORT||8870)],['franka',Number(process.env.REMOTE_TEST_PORT||8871)]]){
   hold=true;const page=await browser.newPage({viewport:{width:1280,height:720}}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>localStorage.setItem('station-language','zh-CN'));
   await page.route('**/video/**',route=>route.continue({url:media+(route.request().url().endsWith('/head_image')?'/head.mp4':'/wrist.mp4')}));
   await page.goto('http://127.0.0.1:'+port+'/#review');
   await page.waitForFunction(()=>document.querySelector('#frames iframe')?.contentWindow.location.pathname.startsWith('/s/'));
   const frame=page.frames().find(f=>f.url().includes('/s/'));
   await frame.waitForSelector('#reviewPlayer');await frame.locator('[data-review-side=A]').click();
   const overlay=frame.locator('[data-review-panel=A] .video-buffering');
   assert.equal(await overlay.isVisible(),false);
   await frame.locator('[data-play=A]').click();
   await frame.waitForFunction(()=>{
    const v=document.querySelector('video.vmain[data-side=A]');
    return v.currentTime>1&&v.readyState<3&&document.querySelector('[data-playstate=A]').dataset.buffering==='true';
   },null,{timeout:20000});
   assert.equal(await overlay.isVisible(),true);assert.ok((await overlay.innerText()).includes('视频缓冲中'));
   assert.equal(await overlay.locator('.buffer-spinner').evaluate(e=>getComputedStyle(e).animationName),'review-buffer-spin');
   await frame.locator('[data-pause=A]').click();await frame.waitForFunction(()=>document.querySelector('[data-playstate=A]').dataset.buffering==='false');
   assert.equal(await overlay.isVisible(),false);
   await frame.locator('[data-play=A]').click();await frame.waitForFunction(()=>document.querySelector('[data-playstate=A]').dataset.buffering==='true');
   const stoppedTime=await frame.locator('video.vmain[data-side=A]').evaluate(v=>v.currentTime);
   hold=false;
   await frame.waitForFunction(t=>document.querySelector('video.vmain[data-side=A]').currentTime>t+1,stoppedTime,{timeout:15000});
   assert.equal(await overlay.isVisible(),false);
   await frame.locator('[data-pause=A]').click();assert.equal(await overlay.isVisible(),false);
   await frame.locator('[data-review-side=B]').click();assert.equal(await overlay.isVisible(),false);
   assert.deepEqual(errors,[]);results.push({robot,real_stream_wait:true,spinner_visible:true,chinese_label:true,pause_hides:true,recovery_hides:true,tab_switch_hides:true});
   await page.close();
  }
  console.log(JSON.stringify(results));
 }finally{await browser.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve))}
})().catch(e=>{console.error(e);server.closeAllConnections();server.close();process.exitCode=1});
