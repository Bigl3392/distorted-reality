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
 let browser;
 try {
  browser=await chromium.launch({headless:true,args:['--disable-background-networking','--disable-component-update','--disable-domain-reliability','--disable-sync','--no-first-run','--no-default-browser-check','--disable-features=MediaRouter,OptimizationHints','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
  artifacts.browser={playwright:require(path.join(pwPath,'package.json')).version,version:browser.version(),executable:chromium.executablePath()};
  for(const scenario of ['complete','correction','tie','incomplete','refusal']){
   const ln=await launch(scenario), base=ln.ready.base_url;
   const requests=[],responses=[],errors=[],denied=[];
   const ctx=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block',recordHar:{path:path.join(out,scenario+'.har'),content:'omit'}});
   await ctx.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin!==base){denied.push(u.origin);return route.abort('blockedbyclient');}return route.continue();});
   await ctx.tracing.start({screenshots:true,snapshots:true,sources:true});
   const page=await ctx.newPage();page.setDefaultTimeout(15000);
   page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
   page.on('response',r=>responses.push({status:r.status(),url:r.url()}));
   page.on('pageerror',e=>errors.push(String(e)));
   try{
    await row(scenario+': boot/provenance',async()=>{
     await page.goto(base);
     await page.getByTestId('heartbeat-status').filter({hasText:'CONTROL: HEALTHY'}).waitFor();
     const text=await page.getByTestId('data-source-provenance').innerText();
     assert.ok(text.includes(new URL(base).host),text);assert.ok(!text.includes('MOCK'),text);
     await page.getByTestId('synthetic-banner').waitFor();
     return text;
    });
    if(scenario==='complete') await row('complete: empty recorded archive',async()=>{
     await page.getByTestId('open-recorded-runs-btn').click();
     await page.getByTestId('empty-recorded-runs-msg').waitFor();
     assert.equal(await page.getByTestId('load-recorded-run-btn').isEnabled(),false);
     await page.getByTestId('close-recorded-modal-btn').click();
    });
    let scan,runId;
    await row(scenario+': dataset MRI and 15-answer scan',async()=>{
     const creating=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/runs'));
     await page.getByTestId('run-mri-btn').click();runId=(await (await creating).json()).run_id;
     await page.getByTestId('mri-steps-table').waitFor();
     await page.getByTestId('proceed-to-stage-2-btn').click();
     const qs=page.locator('[data-testid^="question-"]');await qs.first().waitFor();
     const ids=await qs.evaluateAll(els=>els.map(e=>e.dataset.testid.slice(9)));
     assert.equal(ids.length,15);
     for(const id of ids.slice(0,14))await page.getByTestId('q-'+id+'-opt-3').click();
     assert.equal(await page.getByTestId('submit-intake-btn').isEnabled(),false);
     assert.equal(requests.filter(r=>r.method==='POST'&&r.url.endsWith('/intake')).length,0);
     await page.getByTestId('q-'+ids[14]+'-opt-3').click();
     const pending=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/intake'));
     await page.getByTestId('submit-intake-btn').click();const res=await pending;assert.equal(res.status(),200);scan=await res.json();
     await page.getByTestId('scan-results-card').waitFor();
     const result=await page.getByTestId('scan-results-card').innerText();
     fs.writeFileSync(path.join(out,scenario+'-scan.json'),JSON.stringify({api:scan,display:result},null,2));
     await page.screenshot({path:path.join(out,scenario+'-scan.png'),fullPage:true});
     return {answerCount:15,apiStatus:res.status(),display:result};
    });
    await row(scenario+': council start is available after SCAN_DONE',async()=>{
     await page.getByTestId('proceed-to-stage-3-btn').click();
     const btn=page.getByTestId('convene-council-btn');await btn.waitFor();
     await page.screenshot({path:path.join(out,scenario+'-council.png'),fullPage:true});
     const dom=await page.locator('body').innerText();
     const backend=await ctx.request.get(base+'/api/v1/runs/'+runId);const state=await backend.json();
     fs.writeFileSync(path.join(out,scenario+'-backend-state.json'),JSON.stringify(state,null,2));assert.equal(state.state,'SCAN_DONE');
     fs.writeFileSync(path.join(out,scenario+'-council.txt'),dom);
     assert.equal(await btn.isEnabled(),true,'Convene button disabled at SCAN_DONE; no start request emitted. '+dom.slice(-1800));
     return {available:true};
    });
    const latest=rows.at(-1);
    if(latest.status==='FAIL') rows.push({name:scenario+': council/executions/packet/approval/download browser journey',status:'BLOCKED',reason:'Stage 3 start gate failed; no forced click or API substitute used'});
    assert.equal(requests.filter(r=>r.method==='POST'&&r.url.endsWith('/start')).length,0);
    if(scenario==='complete'){
     
     await row('AT-03: all 76 backend scoring vectors displayed verbatim',async()=>{
      const shared=JSON.parse(fs.readFileSync(path.join(path.dirname(summaryFile),'..','..','..','..','workspace','distorted-reality','scan','vectors.json'),'utf8'));
      const evidence=[];
      for(const [sum,expected] of Object.entries(shared.total_to_overall)){
       await page.goto(base);await page.getByTestId('run-mri-btn').click();await page.getByTestId('mri-steps-table').waitFor();await page.getByTestId('proceed-to-stage-2-btn').click();
       const qs=page.locator('[data-testid^="question-"]');await qs.first().waitFor();const ids=await qs.evaluateAll(els=>els.map(e=>e.dataset.testid.slice(9)));
       let remainder=Number(sum)-15;const answers=[];
       for(const id of ids){let value=1+Math.min(5,remainder);remainder-=value-1;answers.push(value);await page.getByTestId('q-'+id+'-opt-'+value).click();}
       const pending=page.waitForResponse(r=>r.url().endsWith('/intake')&&r.request().method()==='POST');await page.getByTestId('submit-intake-btn').click();
       const response=await pending;assert.equal(response.status(),200);const result=await response.json();await page.getByTestId('scan-results-card').waitFor();
       assert.equal(result.overall,expected);assert.equal((await page.getByTestId('overall-index-value').innerText()).trim(),String(result.overall));
       assert.equal(await page.getByTestId('generic-recommendation').innerText(),result.recommendation);
       const body=await page.getByTestId('scan-results-card').innerText();
       for(const text of result.limitations)assert.ok(body.includes(text),'missing API limitation');
       assert.equal(await page.locator('[data-testid^="question-"]').count(),0);
       assert.ok(!Object.hasOwn(result,'answers'));assert.ok(!Object.hasOwn(result,'systems'));
       evidence.push({sum:Number(sum),expected,api:result,display:body});
       fs.writeFileSync(path.join(out,'76-vectors.json'),JSON.stringify(evidence,null,2));
       if(evidence.length%10===0)console.log('AT03 vectors',evidence.length);
      }
      assert.equal(evidence.length,76);return {vectors:76};
     });

     await ln.stop();ln.stopped=true;
     await row('backend shutdown: heartbeat and no automatic mock fallback',async()=>{
      await page.getByTestId('heartbeat-status').filter({hasText:'CONTROL: UNREACHABLE'}).waitFor({timeout:15000});
      assert.ok((await page.getByTestId('heartbeat-status').innerText()).includes(new URL(base).host));
      assert.ok(!(await page.getByTestId('data-source-provenance').innerText()).includes('MOCK'));
      await page.screenshot({path:path.join(out,'backend-unreachable.png'),fullPage:true});
     });
    }
   }finally{
    fs.writeFileSync(path.join(out,scenario+'-network.json'),JSON.stringify({requests,responses,errors,denied},null,2));
    rows.push({name:scenario+': browser origin and runtime errors',status:denied.length===0&&errors.length===0?'PASS':'FAIL',denied,errors});
    await ctx.tracing.stop({path:path.join(out,scenario+'-trace.zip')});await ctx.close();if(!ln.stopped)await ln.stop();save();
   }
  }
  const ln=await launch('complete','UNSET'),ctx=await browser.newContext({serviceWorkers:'block'});
  try{
   const page=await ctx.newPage();await ctx.route('**/*',r=>new URL(r.request().url()).origin===ln.ready.base_url?r.continue():r.abort());
   await row('UNSET per-IP: browser create refuses 503',async()=>{
    await page.goto(ln.ready.base_url);await page.getByTestId('run-mri-btn').waitFor();
    const pending=page.waitForResponse(r=>r.url().endsWith('/runs')&&r.request().method()==='POST');
    await page.getByTestId('run-mri-btn').click();const response=await pending;assert.equal(response.status(),503);
    await page.screenshot({path:path.join(out,'unset-refusal.png'),fullPage:true});return await response.json();
   });
  }finally{await ctx.close();await ln.stop();}
 }catch(e){artifacts.fatal=String(e.stack||e);console.error(artifacts.fatal);}
 finally{if(browser)await browser.close();save();}
 process.exitCode=artifacts.fatal||rows.some(r=>r.status==='FAIL')?1:0;
})();
