// Real CLI load probe. Never prepares or publishes tickets, changes roles, or deletes data.
import fs from 'node:fs';
import {parseArgs} from 'node:util';
import {chromium} from '../../frontend/node_modules/playwright/index.mjs';

const {values}=parseArgs({options:{base:{type:'string',default:'http://localhost:3000'},environment:{type:'string'},parallel:{type:'string',default:'5'},rounds:{type:'string',default:'1'},output:{type:'string'},'allow-inference':{type:'boolean',default:false},'timeout-seconds':{type:'string',default:'1200'}}});
const parallel=Number(values.parallel), rounds=Number(values.rounds), timeout=Number(values['timeout-seconds']);
const base=new URL(values.base);
if(!values['allow-inference']||!values.environment||!values.output||![5,10].includes(parallel)||!Number.isInteger(rounds)||rounds<1||rounds>20||!Number.isFinite(timeout)||timeout<30||timeout>3600||!['localhost','127.0.0.1'].includes(base.hostname))throw Error('Use a dedicated local test environment, --parallel 5|10, --output and explicit --allow-inference. Native AI quota will be consumed.');
const questions=['Quel framework utilise le backend ?', 'Quel framework utilise le frontend ?', 'Quelle base stocke les conversations ?', 'Quel outil sert les requêtes HTTP Django ?', 'Quel outil exécute les tests backend ?', 'Quel outil exécute les tests navigateur ?', 'Quel outil orchestre les conteneurs locaux ?', 'Quel format utilisent les rapports textuels ?', 'Quel langage utilise le backend ?', 'Quel langage utilise principalement le frontend ?'];
const report={kind:'real-native-conversation-load',parallel,rounds,started_at:new Date().toISOString(),environment_id:Number(values.environment),operations:[],limits:['No external publication is performed','Native provider quotas and current connection capacity are preserved','Small samples do not establish p95/p99 service guarantees']};
const save=()=>fs.writeFileSync(values.output,JSON.stringify(report,null,2)+'\n');
const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',headless:true});
try{
 const page=await browser.newPage();await page.goto(base.href+'analyses');
 const access=await(await page.request.get(new URL('/api/access/session',base).href)).json();
 if(!access.authenticated)throw Error('Authenticate this local test session first');
 const headers={'X-CSRFToken':access.csrf_token||'',Origin:base.origin};
 async function call(path,data){const response=await page.request.post(new URL('/api'+path,base).href,{data,headers});if(!response.ok())throw Error('Request rejected: '+response.status());return response.json();}
 async function get(path){const response=await page.request.get(new URL('/api'+path,base).href);if(!response.ok())throw Error('Read rejected: '+response.status());return response.json();}
 const environment=(await get('/environments')).find(item=>item.id===Number(values.environment));
 if(!environment||environment.status!=='READY')throw Error('Dedicated environment must be ready');
 for(let round=0;round<rounds;round++){
  const batch=await Promise.all(questions.slice(0,parallel).map(async(question,index)=>{
   const marker=`LOAD-${Date.now()}-${round}-${index}`;
   const value=await call('/analyses',{environment_id:environment.id,need:`${question} Consulte uniquement les manifestes nécessaires de SpecHelper. Réponds en une phrase concise en incluant le marqueur ${marker}. Ne prépare ni ticket ni analyse approfondie.`});
   const operation={id:value.id,marker,round,index,submitted_at:new Date().toISOString(),started_at:null,finished_at:null,status:'SUBMITTING',connection_id:null,foreign_marker:false};
   report.operations.push(operation);save();
   const launched=await call('/analyses/'+value.id+'/analyze');
   operation.connection_id=launched.discussion?.connection_id;operation.status='QUEUED';save();return operation;
  }));
  const deadline=Date.now()+timeout*1000;
  while(batch.some(operation=>!operation.finished_at)&&Date.now()<deadline){
   await Promise.all(batch.filter(operation=>!operation.finished_at).map(async operation=>{
    const value=await get('/analyses/'+operation.id), job=value.work_progress?.filter(item=>item.kind==='discussion').at(-1)||value.discussion?.job;
    operation.error=value.error||'';
    operation.status=job?.status||value.conversation_state||value.status;
    operation.started_at=job?.started_at||operation.started_at;
    const replyMessage=value.messages?.filter(message=>message.kind==='discussion_reply').at(-1);
    const reply=replyMessage?.content;
    if(replyMessage){operation.context_id=replyMessage.data?.context_id;operation.native_session_id=replyMessage.data?.native_session_id;}
    if(reply){operation.foreign_marker=report.operations.some(other=>other.id!==operation.id&&reply.includes(other.marker));operation.own_marker=reply.includes(operation.marker);}
    if(['DONE','ERROR','CANCELLED'].includes(job?.status)||value.conversation_state==='AWAITING_REPLY'){
     operation.finished_at=job?.finished_at||new Date().toISOString();
     operation.latency_seconds=(Date.parse(operation.finished_at)-Date.parse(operation.submitted_at))/1000;
     operation.queue_seconds=operation.started_at?(Date.parse(operation.started_at)-Date.parse(operation.submitted_at))/1000:null;
    }
   }));save();
   if(batch.some(operation=>!operation.finished_at))await new Promise(resolve=>setTimeout(resolve,5000));
  }
  if(batch.some(operation=>!operation.finished_at)){report.timed_out=true;break;}
 }
 report.finished_at=new Date().toISOString();
 report.summary={operations:report.operations.length,done:report.operations.filter(item=>item.status==='DONE').length,errors:report.operations.filter(item=>item.status==='ERROR').length,cancelled:report.operations.filter(item=>item.status==='CANCELLED').length,missing_markers:report.operations.filter(item=>item.status==='DONE'&&!item.own_marker).length,foreign_markers:report.operations.filter(item=>item.foreign_marker).length,pending:report.operations.filter(item=>!item.finished_at).length};
 save();console.log(JSON.stringify(report.summary));
 if(report.summary.done!==report.summary.operations||report.summary.pending||report.summary.errors||report.summary.foreign_markers||report.summary.missing_markers)process.exitCode=1;
}catch(error){
 report.transport_failure=error.name||'Error';report.finished_at=new Date().toISOString();save();console.log(JSON.stringify({transport_failure:report.transport_failure,pending:report.operations.filter(item=>!item.finished_at).length}));process.exitCode=1;
}finally{await browser.close();}
