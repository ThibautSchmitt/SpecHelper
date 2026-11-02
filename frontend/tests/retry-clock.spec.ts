import {test,expect} from './fixtures';

const id='56565656-5656-4565-8565-565656565656';
const original='2026-11-02T09:00:00Z';
test('retry clocks reset together, tick locally, survive reload and stop during waits',async({page})=>{
 await page.clock.install({time:new Date('2026-11-02T10:59:59Z')});
 await page.clock.pauseAt(new Date('2026-11-02T11:00:00Z'));
 let clock={seconds:7,observed_at:'2026-11-02T11:00:00Z',running:true};
 let state='RUNNING';
 const run=()=>({number:1,status:state==='QUEUED'?'QUEUED':'RUNNING',started_at:original,steps:[],execution:{status:state==='QUEUED'?'QUEUED':'ANALYZING',current_role:'analyst',checkpoint:'analyst',waiting_reason:state==='QUEUED'?'Waiting for an AI execution slot.':'',stages:[{role:'analyst',status:state==='QUEUED'?'blocked':'running'},{role:'counter_analyst',status:'not_started'},{role:'verifier',status:'not_started'}]}});
 const work=()=>({id:22,kind:'analysis',status:state,run_number:1,created_at:original,started_at:original,finished_at:null,analysis_clock:clock,phases:[],waiting_reason:state==='QUEUED'?'Waiting for an AI execution slot.':''});
 const value=()=>({id,title:'Fictional dates',need:'Explain dates.',workflow:'question',environment_name:'Staging',status:state==='QUEUED'?'QUEUED':'ANALYZING',created_at:original,analysis_protocol:'2.4',baseline:[],database:{},attachments:[],progress:[],questions:[],conversation:[],versions:[],latest_version:null,decisions:[],decision_history:[],messages:[{id:1,role:'user',kind:'need',content:'Explain dates.',created_at:original}],analysis_runs:[run()],work_progress:[work()],discussion:{enabled:true,mode:'analysis',revision:1,job:null}});
 await page.route('**/api/**',r=>r.fulfill({json:[]}));
 await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
 await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language:'en'}}));
 await page.route('**/api/queue',r=>r.fulfill({json:[{...work(),title:'Fictional dates',queue_state:state,public_role:'analyst',href:`/analyses/${id}`,active_analysis_seconds:3607,can_cancel:false}]}));
 await page.route(`**/api/analyses/${id}`,r=>r.fulfill({json:value()}));
 await page.route(`**/api/analyses/${id}/progress?*`,r=>r.fulfill({json:{unchanged:true}}));
 await page.goto(`/analyses/${id}`);
 const elapsed=page.locator('.investigation-progress .work-elapsed');
 await expect(elapsed).toHaveText('0:07');
 if(!await page.locator('.queue-card:visible').count())await page.getByRole('button',{name:'Activity',exact:true}).click();
 await expect(page.locator('.queue-card:visible')).toContainText('Active AI: 0m 7s');
 await page.clock.runFor(2000);
 await expect(elapsed).toHaveText('0:09');
 await expect(page.locator('.queue-card:visible')).toContainText('Active AI: 0m 9s');
 // A fresh retry must override both the old cycle start and legacy accumulated total.
 clock={seconds:0,observed_at:'2026-11-02T11:00:02Z',running:true};
 await page.reload();
 await expect(elapsed).toHaveText('0:00');
 if(!await page.locator('.queue-card:visible').count())await page.getByRole('button',{name:'Activity',exact:true}).click();
 await expect(page.locator('.queue-card:visible')).toContainText('Active AI: 0m 0s');
 state='QUEUED';clock={seconds:2,observed_at:'2026-11-02T11:00:04Z',running:false};
 await page.reload();
 await expect(elapsed).toHaveCount(0);
 await page.clock.runFor(60000);
 await expect(elapsed).toHaveCount(0);
 await expect(page.locator('.investigation-progress')).toContainText('Waiting for an available assistant');
});
