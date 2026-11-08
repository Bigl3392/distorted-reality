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
 try{
  browser=await chromium.launch({headless:true,args:['--disable-background-networking','--disable-component-update','--disable-domain-reliability','--disable-sync','--no-first-run','--disable-features=MediaRouter,OptimizationHints','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
  artifacts.browser={playwright:require(path.join(pwPath,'package.json')).version,version:browser.version(),executable:chromium.executablePath()};
  for(const scenario of (process.env.M12_SCENARIOS ? process.env.M12_SCENARIOS.split(',') : ['complete','correction','tie','incomplete','refusal'])){
   const ln=await launch(scenario),base=ln.ready.base_url;
   const ctx=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block',recordHar:{path:path.join(out,scenario+'.har'),content:'embed'}});
   const requests=[],errors=[],denied=[],responses=[];
   await ctx.route('**/*',r=>{if(new URL(r.request().url()).origin===base)return r.continue();denied.push(r.request().url());return r.abort();});
   await ctx.tracing.start({screenshots:true,snapshots:true,sources:true});
   const page=await ctx.newPage();page.setDefaultTimeout(12000);page.on('pageerror',e=>errors.push(String(e)));
   page.on('request',r=>requests.push({method:r.method(),url:r.url(),body:r.method()==='POST'?r.postData():undefined}));
   page.on('response',r=>responses.push({status:r.status(),url:r.url()}));
   let rid,packet,council;
   const shot=async name=>{await page.screenshot({path:path.join(out,scenario+'-'+name+'.png'),fullPage:true});fs.writeFileSync(path.join(out,scenario+'-'+name+'.txt'),await page.locator('body').innerText());};
   async function check(name,fn){await row(scenario+': '+name,fn);return rows.at(-1).status==='PASS';}
   try{
    const initialized=await check('production boot and serving origin',async()=>{
     await page.goto(base);await page.getByTestId('heartbeat-status').filter({hasText:'CONTROL: HEALTHY'}).waitFor();
     assert.ok((await page.getByTestId('data-source-provenance').innerText()).includes(new URL(base).host));
     assert.ok(!(await page.locator('body').innerText()).includes('MOCK DEV HARNESS'));
     await page.getByTestId('synthetic-banner').waitFor();return base;
    });
    if(!initialized)continue;
    if(scenario==='complete')await check('archive stays empty',async()=>{
     await page.getByTestId('open-recorded-runs-btn').click();await page.getByTestId('empty-recorded-runs-msg').waitFor();
     assert.equal(await page.getByTestId('load-recorded-run-btn').isEnabled(),false);await page.getByTestId('close-recorded-modal-btn').click();
    });
    const scanned=await check('MRI, fourteen-answer block, fifteen-answer scan and every limitation',async()=>{
     const created=page.waitForResponse(r=>r.url().endsWith('/runs')&&r.request().method()==='POST');await page.getByTestId('run-mri-btn').click();
     const r=await created;assert.equal(r.status(),201);const creation=await r.json();rid=creation.run_id;
     await page.getByTestId('mri-steps-table').waitFor();assert.ok((await page.locator('body').innerText()).includes('authorizes nothing'));
     assert.equal(await page.locator('input[type=file]').count(),0);await page.getByTestId('proceed-to-stage-2-btn').click();
     const qs=page.locator('[data-testid^="question-"]');await qs.first().waitFor();const ids=await qs.evaluateAll(es=>es.map(e=>e.dataset.testid.slice(9)));assert.equal(ids.length,15);
     for(const id of ids.slice(0,14))await page.getByTestId('q-'+id+'-opt-3').click();
     assert.equal(await page.getByTestId('submit-intake-btn').isEnabled(),false);
     assert.equal(requests.filter(r=>r.method==='POST'&&r.url.endsWith('/intake')).length,0);
     await page.getByTestId('q-'+ids[14]+'-opt-3').click();const pending=page.waitForResponse(r=>r.url().endsWith('/intake')&&r.request().method()==='POST');
     await page.getByTestId('submit-intake-btn').click();const resultResponse=await pending;assert.equal(resultResponse.status(),200);const scan=await resultResponse.json();
     await page.getByTestId('scan-results-card').waitFor();const display=await page.getByTestId('scan-results-card').innerText();
     fs.writeFileSync(path.join(out,scenario+'-scan.json'),JSON.stringify({api:scan,display},null,2));
     assert.equal((await page.getByTestId('overall-index-value').innerText()).trim(),String(scan.overall));
     assert.equal(await page.getByTestId('generic-recommendation').innerText(),scan.recommendation);
     for(const lim of scan.limitations)assert.ok(display.includes(lim),'Missing API limitation: '+lim);
     assert.equal(await qs.count(),0);await shot('scan');
    });
    if(!scanned){rows.push({name:scenario+': remaining journey',status:'BLOCKED',reason:'intake did not complete'});continue;}
    const started=await check('SCAN_DONE button enabled and ordinary click sends start',async()=>{
     await page.getByTestId('proceed-to-stage-3-btn').click();const btn=page.getByTestId('convene-council-btn');assert.equal(await btn.isEnabled(),true);
     assert.ok((await page.locator('body').innerText()).includes('READY TO CONVENE'));
     const pending=page.waitForResponse(r=>r.url().endsWith('/start')&&r.request().method()==='POST');await btn.click();const response=await pending;
     assert.equal(response.status(),scenario==='refusal'?409:202);return {status:response.status(),body:await response.json()};
    });
    if(!started){rows.push({name:scenario+': remaining journey',status:'BLOCKED',reason:'start failed'});continue;}
    if(scenario==='refusal'){
     await check('409 refusal offers empty genuine archive without fabricated packet',async()=>{
      await page.getByTestId('recorded-runs-modal').waitFor();await page.getByTestId('empty-recorded-runs-msg').waitFor();
      assert.equal(await page.getByTestId('load-recorded-run-btn').isEnabled(),false);await shot('refusal');
     });continue;
    }
    let arrived;
    if(scenario==='incomplete'){
     arrived=await check('failed run reaches INCOMPLETE packet',async()=>{await page.getByTestId('incomplete-packet-alert').waitFor({timeout:30000});await shot('packet');});
    }else{
     arrived=await check('council completes and packet viewer is reachable',async()=>{
      await page.getByTestId('proceed-to-stage-4-btn').waitFor({timeout:30000});
      const rr=await ctx.request.get(base+'/api/v1/runs/'+rid+'/council');assert.equal(rr.status(),200);council=await rr.json();
      fs.writeFileSync(path.join(out,scenario+'-council.json'),JSON.stringify(council,null,2));await shot('council');
      await page.getByTestId('proceed-to-stage-4-btn').click();await page.getByTestId('claim-discipline-statement').waitFor();
     });
     await check('three actual paths and valid confidence are displayed',async()=>{
      assert.ok(council,'No council readback');
      // Captured Stage 3 DOM before navigating, not a fabricated or API-backed replacement UI.
      const text=fs.readFileSync(path.join(out,scenario+'-council.txt'),'utf8');
      const paths=council.revision?.paths||council.initial_paths;
      const list=Array.isArray(paths)?paths:paths?.paths;assert.equal(list.length,3);
      for(const p of list)assert.ok(text.includes(p.intervention.summary),'Missing path intervention '+p.path_id);
      assert.ok(!text.includes('NaN%'),'Non-numeric confidence displayed as NaN%');
     });
    }
    if(!arrived){await shot('blocked');rows.push({name:scenario+': packet/approval/download',status:'BLOCKED',reason:'packet UI not reachable'});continue;}
    await check('packet sections preserve required honesty text',async()=>{
     const response=await ctx.request.get(base+'/api/v1/runs/'+rid+'/packet');assert.equal(response.status(),200);packet=await response.json();
     fs.writeFileSync(path.join(out,scenario+'-packet.json'),JSON.stringify(packet,null,2));await shot('packet');
     const text=await page.locator('body').innerText();const missing=[];
     for(const k of ['claim_statement','synthetic_notice','assumptions','unknowns','did_not_prove','limitations']){
      const list=Array.isArray(packet[k])?packet[k]:[packet[k]];for(const value of list)if(value&&!text.includes(value))missing.push({field:k,text:value});
     }
     artifacts[scenario+'MissingPacketText']=missing;assert.deepEqual(missing,[]);
    });
    if(scenario==='incomplete'){rows.push({name:'incomplete: approval not applicable; download UI coverage',status:'NOT_RUN',reason:'No forced navigation or API writes to bypass failed-state UI'});continue;}
    await check('rule outcome, receipt metrics and tie display match packet',async()=>{
     assert.ok(packet);const rule=await page.getByTestId('decision-rule-card').innerText();assert.ok(rule.includes(packet.outcome.result));assert.ok(rule.includes(packet.outcome.preferred_path_id||'NONE'));
     if(scenario==='tie'){assert.equal(packet.outcome.preferred_path_id,null);assert.equal(packet.outcome.result,'NO_SUFFICIENT_EVIDENCE');}
     const table=page.getByTestId('recomputed-metrics-table');assert.equal(await table.locator('tbody tr').count(),packet.executions.length);
     for(let i=0;i<packet.executions.length;i++){const cells=await table.locator('tbody tr').nth(i).locator('td').allTextContents();const m=packet.executions[i].metrics_recomputed;assert.equal(Number(cells[1]),m.exceptions_caught);assert.equal(Number(cells[2]),m.false_alarms);assert.equal(Number(cells[3]),m.unsupported_claims);}
    });
    const approval=await check('view then confirm is available through the browser',async()=>{
     await page.getByTestId('proceed-to-stage-5-btn').click();const confirm=page.getByTestId('confirm-approval-btn');assert.equal(await confirm.isEnabled(),false);
     const pending=page.waitForResponse(r=>r.url().endsWith('/approve')&&r.request().method()==='POST');await page.getByTestId('view-packet-btn').click();
     const response=await pending;assert.equal(response.status(),200);const viewed=await response.json();fs.writeFileSync(path.join(out,scenario+'-view-response.json'),JSON.stringify(viewed,null,2));
     await page.getByTestId('view-packet-btn').filter({hasText:'Packet Inspected'}).waitFor({timeout:3000});
     assert.equal(await confirm.isEnabled(),true);await shot('viewed');
     const confirming=page.waitForResponse(r=>r.url().endsWith('/approve')&&r.request().method()==='POST');await confirm.click();const sealed=await (await confirming).json();
     assert.equal(sealed.packet.approval_gate.external_action_taken,false);assert.equal(sealed.packet.approval_gate.status,'VIEWED_CONFIRMED');
     assert.equal(await confirm.isEnabled(),false);await shot('approved');
    });
    if(!approval){await shot('approval-blocked');rows.push({name:scenario+': confirmed download journey',status:'BLOCKED',reason:'view/confirm did not complete; no API substitute'});}
    else await check('four browser downloads after human review',async()=>{
     await page.getByTestId('generate-token-btn').click();
     for(const part of ['packet','journal','events','rule']){
      const link=page.getByTestId('download-link-'+part);await link.waitFor();const download=page.waitForEvent('download');await link.click();const file=await download;await file.saveAs(path.join(out,scenario+'-download-'+part));assert.equal(await file.failure(),null);
     }
     assert.equal(requests.filter(r=>new URL(r.url).origin!==base).length,0);
    });
   }finally{
    await shot('final').catch(()=>{});fs.writeFileSync(path.join(out,scenario+'-network.json'),JSON.stringify({requests,responses,errors,denied},null,2));
    rows.push({name:scenario+': network stays at serving origin; no page errors',status:denied.length===0&&errors.length===0?'PASS':'FAIL',errors,denied});
    await ctx.tracing.stop({path:path.join(out,scenario+'-trace.zip')});await ctx.close();await ln.stop();save();
   }
  }
 }catch(e){artifacts.fatal=String(e.stack||e);console.error(artifacts.fatal);}
 finally{if(browser)await browser.close();save();}
 process.exitCode=artifacts.fatal||rows.some(r=>r.status==='FAIL')?1:0;
})();
