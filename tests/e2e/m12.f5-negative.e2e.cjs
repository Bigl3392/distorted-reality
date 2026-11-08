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
 for(let i=0;i<1800;i++){const line=stdout.split('\n').find(l=>l.trim().startsWith('{'));if(line){ready=JSON.parse(line);break;}if(exit!==undefined)throw Error('Launcher exited '+exit+': '+stderr);await pause(100);}
 if(!ready){proc.stdin.end();await Promise.race([exited,pause(10000)]);throw Error('Local launcher readiness timeout after 180 test-only seconds; stdin closed for fake teardown: '+stderr);}
 const record={scenario,ready};artifacts.launches.push(record);save();
 return {ready,async stop(){proc.stdin.end();let code=await Promise.race([exited,pause(15000).then(()=>undefined)]);record.exit=code;record.stdout=stdout;record.stderr=stderr;save();assert.equal(code,0,'launcher clean exit');}};
}
(async()=>{
 let browser;
 try{
  browser=await chromium.launch({headless:true,args:['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run','--disable-features=MediaRouter,OptimizationHints','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
  artifacts.browser={playwright:require(path.join(pwPath,'package.json')).version,version:browser.version(),executable:chromium.executablePath()};
  for(const mode of ['transient','unbuildable']){
   const stats=path.resolve(out,mode+'-stats.jsonl');const linuxStats='/mnt/'+stats[0].toLowerCase()+stats.slice(2).replaceAll('\\','/');
   const launcher=path.resolve(__dirname,'f5_negative_launcher.py');const linuxLauncher='/mnt/'+launcher[0].toLowerCase()+launcher.slice(2).replaceAll('\\','/');
   const args=['-d','Ubuntu','--','env','PYTHONDONTWRITEBYTECODE=1','PYTHONPATH='+envInfo.scratch+'/guard','WALTER_NETWORK_AUDIT='+envInfo.scratch+'/browser-network',
    envInfo.python,'-B',linuxLauncher,'--snapshot',envInfo.stage,'--mode',mode,'--stats',linuxStats];
   const proc=cp.spawn('wsl.exe',args,{windowsHide:true,stdio:['pipe','pipe','pipe']});
   let stdout='',stderr='',exitCode;proc.stdout.on('data',b=>stdout+=b);proc.stderr.on('data',b=>stderr+=b);
   const exited=new Promise(resolve=>proc.on('close',code=>{exitCode=code;resolve(code)}));let ready;
   for(let i=0;i<1800;i++){const line=stdout.split('\n').find(x=>x.trim().startsWith('{'));if(line){ready=JSON.parse(line);break;}if(exitCode!==undefined)throw Error(stderr);await pause(100);}
   if(!ready){proc.stdin.end();throw Error('Negative fixture startup timeout');}
   const rec={scenario:mode,ready};artifacts.launches.push(rec);save();
   const base=ready.base_url,ctx=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block',recordHar:{path:path.join(out,mode+'.har'),content:'embed'}});
   const requests=[],responses=[],errors=[],denied=[];
   await ctx.route('**/*',r=>{if(new URL(r.request().url()).origin===base)return r.continue();denied.push(r.request().url());return r.abort()});
   await ctx.tracing.start({screenshots:true,snapshots:true,sources:true});
   const page=await ctx.newPage();page.setDefaultTimeout(15000);
   page.on('request',r=>requests.push({method:r.method(),url:r.url()}));page.on('response',r=>responses.push({status:r.status(),url:r.url()}));page.on('pageerror',e=>errors.push(String(e)));
   try{
    await row(mode+': fixture reaches FAILED_CLOSED through ordinary browser intake/start',async()=>{
     await page.goto(base);await page.getByTestId('run-mri-btn').click();await page.getByTestId('mri-steps-table').waitFor();await page.getByTestId('proceed-to-stage-2-btn').click();
     await page.getByTestId('fill-reference-sample-btn').click();await page.getByTestId('submit-intake-btn').click();await page.getByTestId('scan-results-card').waitFor();
     await page.getByTestId('proceed-to-stage-3-btn').click();await page.getByTestId('convene-council-btn').click();
    });
    await row(mode+': packet recovery or bounded explicit failure',async()=>{
     if(mode==='transient'){
      await page.getByTestId('incomplete-packet-alert').waitFor({timeout:30000});
      const list=responses.filter(x=>x.url.endsWith('/packet'));assert.deepEqual(list.map(x=>x.status),[404,404,200]);
      assert.ok(!(await page.locator('body').innerText()).includes('Awaiting completion of Blackbox execution'));
      return {packetStatuses:list.map(x=>x.status),fault:'first two packet responses deliberately unavailable; third delegates to real API'};
     }
     const end=Date.now()+45000;
     while(responses.filter(x=>x.url.endsWith('/packet')).length<15&&Date.now()<end)await pause(100);
     assert.equal(responses.filter(x=>x.url.endsWith('/packet')).length,15);
     await pause(1200);
     assert.equal(requests.filter(x=>x.url.endsWith('/packet')).length,15,'retry must stop at 15');
     assert.ok(responses.filter(x=>x.url.endsWith('/packet')).every(x=>x.status===404));
     await page.getByTestId('packet-unavailable-alert').waitFor();
     const text=await page.getByTestId('packet-unavailable-alert').innerText();
     assert.ok(text.includes('RUN FAILED CLOSED'));assert.ok(text.includes('ModelMismatch'));assert.ok(!(await page.locator('body').innerText()).includes('Awaiting completion of Blackbox execution'));
     assert.equal(await page.getByTestId('incomplete-packet-alert').count(),0);
     return {packetGets:15,all404:true,alert:text,fault:'packet builder deliberately raises PacketError; API 404s are real'};
    });
   }finally{
    await page.screenshot({path:path.join(out,mode+'.png'),fullPage:true});fs.writeFileSync(path.join(out,mode+'-dom.txt'),await page.locator('body').innerText());
    fs.writeFileSync(path.join(out,mode+'-network.json'),JSON.stringify({requests,responses,errors,denied},null,2));
    rows.push({name:mode+': same origin and no page errors',status:!errors.length&&!denied.length?'PASS':'FAIL',errors,denied});
    await ctx.tracing.stop({path:path.join(out,mode+'-trace.zip')});await ctx.close();
    proc.stdin.end();rec.exit=await Promise.race([exited,pause(15000).then(()=>undefined)]);rec.stdout=stdout;rec.stderr=stderr;save();assert.equal(rec.exit,0);
   }
  }
 }catch(e){artifacts.fatal=String(e.stack||e);console.error(artifacts.fatal)}
 finally{if(browser)await browser.close();save()}
 console.log(JSON.stringify(rows.map(({name,status})=>({name,status}))));process.exitCode=artifacts.fatal||rows.some(r=>r.status==='FAIL')?1:0;
})();
