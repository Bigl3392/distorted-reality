/* Walter M12: real browser, real loopback WSGI, approved fakes only.
   Usage: node m12.e2e.cjs <summary.json> <existing-playwright-package> <artifact-dir>
   No package installation, remote browser, response mocking, DOM alteration or forced click. */
const fs=require('node:fs'), path=require('node:path'), cp=require('node:child_process'), assert=require('node:assert/strict');
const [summaryFile,pwPath,out]=process.argv.slice(2);
if(!summaryFile||!pwPath||!out) throw Error('Three explicit arguments required');
const envInfo=JSON.parse(fs.readFileSync(summaryFile,'utf8'));
const {chromium}=require(pwPath);
fs.mkdirSync(out,{recursive:true});
const rows=[], artifacts={browser:null,launches:[],rows};
function save(){fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(artifacts,null,2));}
function pause(ms){return new Promise(r=>setTimeout(r,ms));}
async function row(name,fn){try{const detail=await fn();rows.push({name,status:'PASS',detail});}catch(e){rows.push({name,status:'FAIL',error:String(e.stack||e)});}save();console.log(name,rows.at(-1).status);}
async function launch(scenario,perip='200',ttl='600'){
 const py=envInfo.python, stage=envInfo.stage, scratch=envInfo.scratch;
 const args=['-d','Ubuntu','--','env','PYTHONDONTWRITEBYTECODE=1','PYTHONPATH='+scratch+'/guard','WALTER_NETWORK_AUDIT='+scratch+'/browser-network',
 'http_proxy=','https_proxy=','all_proxy=','HTTP_PROXY=','HTTPS_PROXY=','ALL_PROXY=',
 py,'-B','-c','import os,runpy;os.chdir('+JSON.stringify(stage)+');runpy.run_module("tests.fakes.launch_fake",run_name="__main__")',
 '--scenario',scenario,'--per-ip-runs-per-hour',perip,'--download-ttl-seconds',ttl,'--exit-on-stdin-eof'];
 const proc=cp.spawn('wsl.exe',args,{windowsHide:true,stdio:['pipe','pipe','pipe']});
 let stdout='',stderr='';proc.stdout.on('data',b=>stdout+=b);proc.stderr.on('data',b=>stderr+=b);
 let exit; const exited=new Promise(r=>proc.on('close',code=>{exit=code;r(code);}));
 let ready;
 for(let i=0;i<300;i++){const line=stdout.split('\n').find(l=>l.trim().startsWith('{'));if(line){ready=JSON.parse(line);break;}if(exit!==undefined)throw Error('Launcher exited '+exit+': '+stderr);await pause(100);}
 if(!ready)throw Error('Local launcher readiness timeout');
 const record={scenario,ready};artifacts.launches.push(record);save();
 return {ready,async stop(){proc.stdin.end();let code=await Promise.race([exited,pause(15000).then(()=>undefined)]);record.exit=code;record.stdout=stdout;record.stderr=stderr;save();assert.equal(code,0,'launcher clean exit');}};
}

(async()=>{
 let browser,ln,ctx;
 try{
  browser=await chromium.launch({headless:true,args:['--disable-background-networking','--disable-component-update','--disable-domain-reliability','--disable-sync','--no-first-run','--disable-features=MediaRouter,OptimizationHints','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
  artifacts.browser={playwright:require(path.join(pwPath,'package.json')).version,version:browser.version(),executable:chromium.executablePath()};
  ln=await launch('complete');const base=ln.ready.base_url;
  ctx=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'});
  const denied=[],errors=[];await ctx.route('**/*',r=>{if(new URL(r.request().url()).origin===base)return r.continue();denied.push(r.request().url());return r.abort();});
  await ctx.tracing.start({screenshots:true,snapshots:true,sources:true});
  const page=await ctx.newPage();page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(String(e)));
  const shared=JSON.parse(fs.readFileSync(path.join(path.dirname(summaryFile),'../../../../workspace/distorted-reality/scan/vectors.json'),'utf8'));
  const evidence=[];const missing=[];
  await row('AT-03 all 76 numeric scores and recommendations match backend/shared vectors',async()=>{
   for(const [sum,expected] of Object.entries(shared.total_to_overall)){
    await page.goto(base);await page.getByTestId('run-mri-btn').click();await page.getByTestId('mri-steps-table').waitFor();await page.getByTestId('proceed-to-stage-2-btn').click();
    const qs=page.locator('[data-testid^="question-"]');await qs.first().waitFor();const ids=await qs.evaluateAll(els=>els.map(e=>e.dataset.testid.slice(9)));assert.equal(ids.length,15);
    let remainder=Number(sum)-15;
    for(const id of ids){const value=1+Math.min(5,remainder);remainder-=value-1;await page.getByTestId('q-'+id+'-opt-'+value).click();}
    const pending=page.waitForResponse(r=>r.url().endsWith('/intake')&&r.request().method()==='POST');await page.getByTestId('submit-intake-btn').click();
    const response=await pending;assert.equal(response.status(),200);const result=await response.json();await page.getByTestId('scan-results-card').waitFor();
    const body=await page.getByTestId('scan-results-card').innerText();
    const absent=result.limitations.filter(t=>!body.includes(t));
    if(absent.length)missing.push({sum,missing:absent});
    evidence.push({sum:Number(sum),expected,api:result,display:body,missing:absent});
    fs.writeFileSync(path.join(out,'76-vectors.json'),JSON.stringify(evidence,null,2));
    assert.equal(result.overall,expected);assert.equal((await page.getByTestId('overall-index-value').innerText()).trim(),String(result.overall));
    assert.equal(await page.getByTestId('generic-recommendation').innerText(),result.recommendation);
    assert.equal(await page.locator('[data-testid^="question-"]').count(),0);
    assert.ok(!Object.hasOwn(result,'answers'));assert.ok(!Object.hasOwn(result,'systems'));
    if(evidence.length===1||evidence.length===76)await page.screenshot({path:path.join(out,'vector-'+sum+'.png'),fullPage:true});
    if(evidence.length%10===0)console.log('AT03 vectors',evidence.length);
   }
   assert.equal(evidence.length,76);return {vectors:76};
  });
  await row('scan limitations preserve API text verbatim',async()=>{artifacts.missingLimitations=missing;assert.deepEqual(missing,[],'The scoring-verifiability limitation is missing from rendered results');});
  await row('reachable keyboard smoke and synthetic bar contrast measurement',async()=>{
   await page.goto(base);await page.getByTestId('run-mri-btn').waitFor();
   const focus=[];for(let i=0;i<8;i++){await page.keyboard.press('Tab');focus.push(await page.evaluate(()=>({tag:document.activeElement.tagName,label:document.activeElement.getAttribute('aria-label'),testid:document.activeElement.dataset.testid})))}
   assert.ok(focus.some(f=>f.testid==='run-mri-btn'));assert.ok(focus.some(f=>f.testid==='open-recorded-runs-btn'));
   const contrast=await page.getByTestId('synthetic-banner').evaluate(el=>{
    const rgb=s=>s.match(/[\d.]+/g).map(Number);
    const chain=[];for(let n=el;n;n=n.parentElement)chain.push(getComputedStyle(n).backgroundColor);
    let bg=[255,255,255];for(const raw of chain.reverse()){const c=rgb(raw),a=c.length>3?c[3]:1;bg=bg.map((v,i)=>c[i]*a+v*(1-a));}
    const fg=rgb(getComputedStyle(el).color),a=fg.length>3?fg[3]:1;const ink=bg.map((v,i)=>fg[i]*a+v*(1-a));
    const lum=c=>c.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
    const x=lum(ink),y=lum(bg);return {textColor:fg,effectiveBackground:bg,ratio:(Math.max(x,y)+.05)/(Math.min(x,y)+.05),scope:'banner inherited text only; no full accessibility audit'};
   });return {focus,contrast};
  });
  rows.push({name:'browser origin and runtime errors',status:denied.length===0&&errors.length===0?'PASS':'FAIL',denied,errors});
 }catch(e){artifacts.fatal=String(e.stack||e);}
 finally{if(ctx){await ctx.tracing.stop({path:path.join(out,'vectors-trace.zip')});await ctx.close();}if(ln)await ln.stop();if(browser)await browser.close();save();}
 console.log(JSON.stringify(rows.map(({name,status})=>({name,status}))));process.exitCode=artifacts.fatal||rows.some(r=>r.status==='FAIL')?1:0;
})();
