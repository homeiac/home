// Read-only browser smoke check of the deployed private cricket page.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1200,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('https://photos.app.home.panderosystems.com/cricket');
  await page.locator('#original option').first().waitFor({state:'attached'});
  const counts=await page.evaluate(async()=>{
   const album=document.querySelector('#album').value;
   const {assets}=await (await fetch('/api/cricket/assets?'+new URLSearchParams({album}))).json();
   const video=assets.find(a=>a.kind==='video');
   const response=await fetch('/api/cricket/media?'+new URLSearchParams({album,asset:video.id}),{headers:{Range:'bytes=0-1023'}});
   return {videos:assets.filter(a=>a.kind==='video').length,photos:assets.filter(a=>a.kind==='photo').length,range:response.status,bytes:(await response.arrayBuffer()).byteLength};
  });
  assert.equal(counts.range,206);assert.equal(counts.bytes,1024);assert.deepEqual(errors,[]);
  await page.screenshot({path:process.argv[2],fullPage:true});
  console.log(JSON.stringify({page:'healthy',...counts}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exit(1);});
