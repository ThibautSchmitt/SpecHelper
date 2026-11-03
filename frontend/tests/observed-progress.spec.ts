import {test,expect} from './fixtures';
import {translate} from '../src/lib/i18n';

const id='41414141-4141-4414-8414-414141414141';
const at='2026-10-30T10:00:00Z';
function dossier(){return {
 id,title:'Benefit behavior',need:'Explain benefits.',original_need:'Explain benefits.',workflow:'question',intent_mode:'auto',environment_name:'Staging',environment_id:1,
 status:'DISCUSSING',result_state:'discussion',created_at:at,analysis_protocol:'2.4',baseline:[],database:{},attachments:[],progress:[],error:'',understanding:'',
 questions:[],conversation:[],latest_version:null,versions:[],decision_revision:0,decisions:[],decision_history:[],validated_version:null,conclusions_stale:false,
 messages:[{id:1,role:'user',kind:'need',content:'Explain benefits.',created_at:at}],
 discussion:{enabled:true,mode:'discussion',revision:1,has_new_messages:true,connection_id:1,job:null},analysis_runs:[],
 progress_token:'content-1',progress_cursor:'cursor-1',work_progress:[],
};}
function phase(){return {id:'phase-1',attempt_id:'attempt-1',role:'discussion',checkpoint:'discussion',sequence:1,activity:'read',preview:'',seen_at:at,closed:false,active:true,events:[{id:'a'.repeat(20),operation:'read',state:'running',observed_at:at}]};}
function job(){return {id:1,kind:'discussion',status:'QUEUED',revision:2,created_at:at,started_at:null,finished_at:null,waiting_reason:'',waiting_causes:[],phases:[]};}

for(const language of ['en','fr'] as const){
 const t=(key:string)=>translate(key,language);
 test(`interrupted analysis stays before later discussion turns and after its clarification in ${language}`,async({page})=>{
  const oldJob={...job(),kind:'analysis',run_number:1,status:'ERROR',started_at:at,finished_at:null};
  let value:any={...dossier(),discussion:{...dossier().discussion,revision:1},messages:[
   ...dossier().messages,
   {id:2,role:'assistant',kind:'clarification',content:'Which period?',created_at:'2026-10-30T10:00:30Z'},
   {id:3,role:'user',kind:'answer',content:'The current period.',created_at:'2026-10-30T10:01:00Z'},
   {id:4,role:'user',kind:'discussion',content:'Explain the exception.',created_at:'2026-10-30T10:03:00Z'},
  ],work_progress:[oldJob],analysis_runs:[{number:1,status:'ERROR',started_at:at,finished_at:null,steps:[
   {public_role:'analyst',status:'ERROR',started_at:at,finished_at:'2026-10-30T10:02:00Z'},
  ]}]};
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language}}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
  await page.route(`**/api/analyses/${id}/progress?*`,route=>route.fulfill({json:{unchanged:true,progress_cursor:value.progress_cursor}}));
  await page.route(`**/api/analyses/${id}/discussion`,route=>{
   const currentJob={...job(),id:2,status:'RUNNING',created_at:'2026-10-30T10:04:01Z',started_at:'2026-10-30T10:04:01Z',phases:[{...phase(),activity:'processing',events:[]}]};
   value={...value,status:'QUEUED',discussion:{...value.discussion,revision:2,job:currentJob},messages:[...value.messages,
    {id:5,role:'user',kind:'discussion',content:'And the previous period?',created_at:'2026-10-30T10:04:00Z'},
   ],work_progress:[oldJob,currentJob]};
   return route.fulfill({json:value});
  });
  await page.goto(`/analyses/${id}`);
  const rows=page.locator('.conversation-messages > li');
  const order=()=>rows.evaluateAll(nodes=>nodes.map(node=>node.getAttribute('data-message')));
  const expected=['message-1','message-2','message-3','progress-1','message-4'];
  await expect(page.locator('[data-message="progress-1"] > article > details > summary')).toContainText(t('Analysis interrupted'));
  await expect.poll(order).toEqual(expected);
  await page.getByLabel(t('Your message'),{exact:true}).fill('And the previous period?');
  await page.getByRole('button',{name:t('Send message'),exact:true}).click();
  await expect(page.locator('.discussion-progress')).toContainText(t('AI is processing…'));
  await expect.poll(order).toEqual([...expected,'message-5','discussion-progress-job-2']);
  await page.reload();
  await expect.poll(order).toEqual([...expected,'message-5','discussion-progress-job-2']);
 });

 test(`streaming follows the bottom without pulling the reader out of history in ${language}`,async({page})=>{
  let value:any={...dossier(),status:'QUEUED',messages:Array.from({length:30},(_,index)=>({id:index+1,role:index%2?'assistant':'user',kind:index%2?'discussion_reply':'discussion',content:`History ${index}\n\n`+'A recorded paragraph. '.repeat(15),created_at:at})),discussion:{...dossier().discussion,job:{...job(),status:'RUNNING'}},work_progress:[{...job(),status:'RUNNING',phases:[{...phase(),preview:'Initial draft.'}]}]};
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language}}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
  await page.route(`**/api/analyses/${id}/progress?*`,route=>route.fulfill({json:{progress_token:value.progress_token,progress_cursor:value.progress_cursor,work_progress:value.work_progress}}));
  await page.goto(`/analyses/${id}`);
  await expect(page.getByLabel(t('Draft response'),{exact:true})).toContainText('Initial draft.');
  const scroller=page.locator(".dashboard-center");
  await scroller.evaluate(node=>node.scrollTo(0,0));
  await expect.poll(()=>scroller.evaluate(node=>node.scrollTop)).toBe(0);
  value={...value,progress_cursor:'cursor-2',work_progress:[{...value.work_progress[0],phases:[{...phase(),preview:'First growth.\n\n'+'A visible paragraph.\n\n'.repeat(20)}]}]};
  await expect(page.getByLabel(t('Draft response'),{exact:true})).toContainText('First growth.');
  expect(await scroller.evaluate(node=>node.scrollTop)).toBeLessThan(50);
  await scroller.evaluate(node=>node.scrollTo(0,node.scrollHeight));
  await expect.poll(()=>scroller.evaluate(node=>node.scrollHeight-node.clientHeight-node.scrollTop)).toBeLessThan(10);
  value={...value,progress_cursor:'cursor-3',work_progress:[{...value.work_progress[0],phases:[{...phase(),preview:'Further growth.\n\n'+'A visible paragraph.\n\n'.repeat(40)}]}]};
  await expect(page.getByLabel(t('Draft response'),{exact:true})).toContainText('Further growth.');
  await expect.poll(()=>scroller.evaluate(node=>node.scrollHeight-node.clientHeight-node.scrollTop)).toBeLessThan(10);
 });
 test(`observed discussion work is immediate, compact, reloadable and uses narrow polling in ${language}`,async({page})=>{
  let value:any=dossier(),fullReads=0,progressReads=0,disconnect=false;
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language,primary_color:'#168e95'}}));
  await page.route(`**/api/analyses/${id}`,route=>{fullReads++;return route.fulfill({json:value});});
  await page.route(`**/api/analyses/${id}/progress?*`,route=>{
   progressReads++;
   if(disconnect)return route.abort('failed');
   const cursor=new URL(route.request().url()).searchParams.get('cursor');
   return route.fulfill({json:cursor===value.progress_cursor ? {unchanged:true,progress_cursor:cursor} : {progress_token:value.progress_token,progress_cursor:value.progress_cursor,work_progress:value.work_progress}});
  });
  await page.route(`**/api/analyses/${id}/discussion`,route=>{
   value={...value,status:'QUEUED',progress_token:'content-2',progress_cursor:'cursor-2',messages:[...value.messages,{id:2,role:'user',kind:'discussion',content:'Explain the exception.',created_at:at}],discussion:{...value.discussion,revision:2,job:{...job(),error:''}},work_progress:[job()]};
   return route.fulfill({json:value});
  });
  await page.goto(`/analyses/${id}`);
  await page.getByLabel(t('Your message'),{exact:true}).fill('Explain the exception.');
  await page.getByRole('button',{name:t('Send message'),exact:true}).click();
  const block=page.locator('.discussion-progress');
  await expect(block).toHaveCount(1);
  await expect(block.locator('.work-progress-static')).toContainText(t('I’m on it…'));
  await expect(block.locator('summary')).toHaveCount(0);
  await expect(block.getByText(t('No detailed work event has been reported.'),{exact:true})).toHaveCount(0);
  const surface=page.getByRole('region',{name:t('Conversation'),exact:true});
  await expect(surface).toHaveAttribute('data-slot','card');
  await expect(surface.getByRole('button',{name:t('Deep analysis'),exact:true})).toBeVisible();
  await expect(surface.getByRole('button',{name:t('Prepare a ticket'),exact:true})).toBeVisible();
  await expect(surface.getByRole('button',{name:t('Cancel'),exact:true})).toBeVisible();
  const readsAfterAccept=fullReads;
  value={...value,progress_cursor:'cursor-3',work_progress:[{...job(),status:'RUNNING',started_at:new Date().toISOString(),phases:[phase()]}]};
  await expect(block.locator('summary')).toContainText(t('Reading source files…'));
  expect(fullReads).toBe(readsAfterAccept);
  await expect(block.locator('.work-observations')).toBeHidden();
  await block.locator('summary').click();
  await expect(block.locator('[data-work-state="running"]')).toContainText(t('Read source files'));
  value={...value,progress_cursor:'cursor-4',work_progress:[{...value.work_progress[0],phases:[{...phase(),sequence:2,activity:'writing',preview:'A **clear** answer.',events:[{...phase().events[0],state:'done'}]}]}]};
  await expect(page.getByLabel(t('Draft response'),{exact:true})).toContainText('A clear answer.');
  await expect(block.locator('[data-work-state="done"]')).toBeVisible();
  expect(fullReads).toBe(readsAfterAccept);
  await page.reload();
  await expect(page.locator('.discussion-progress')).toHaveCount(1);
  await page.locator('.discussion-progress > summary').click();
  await expect(page.locator('[data-work-state="done"]')).toBeVisible();
  disconnect=true;
  await expect(page.locator('.discussion-progress > summary')).toContainText(t('Progress updates unavailable'));
  await expect(page.locator('.discussion-progress > summary .animate-spin')).toHaveCount(0);
  disconnect=false;
  value={...value,status:'DISCUSSING',progress_token:'content-3',progress_cursor:'cursor-5',messages:[...value.messages,{id:3,role:'assistant',kind:'discussion_reply',content:'A clear answer.',created_at:at}],discussion:{...value.discussion,job:{...value.discussion.job,status:'DONE'}},work_progress:[{...value.work_progress[0],status:'DONE',finished_at:at,phases:[{...value.work_progress[0].phases[0],active:false,closed:true,preview:''}]}]};
  await expect(page.locator('.conversation-answer').getByText('A clear answer.',{exact:true})).toBeVisible();
  await expect(page.getByLabel(t('Draft response'),{exact:true})).toHaveCount(0);
  await expect(block.locator('summary')).toContainText(t('Reply completed'));
  expect(progressReads).toBeGreaterThan(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });

 test(`deep work preserves real role states and hides unstarted role details in ${language}`,async({page})=>{
  const analyst={...phase(),role:'analyst',checkpoint:'analyst',active:false,closed:true,events:[{...phase().events[0],state:'done'}]};
  const counter={...phase(),id:'phase-2',role:'counter_analyst',checkpoint:'counter_independent',events:[
   {...phase().events[0],id:'b'.repeat(20),operation:'tool',state:'error'},
   ...['c','d','e'].map(id=>({...phase().events[0],id:id.repeat(20),operation:'tool',state:'done'})),
   {...phase().events[0],id:'f'.repeat(20),operation:'git',state:'running'},
   {...phase().events[0],id:'0'.repeat(20),operation:'command',state:'running'},
  ]};
  const value:any={...dossier(),status:'ANALYZING',discussion:{...dossier().discussion,mode:'analysis'},work_progress:[{...job(),kind:'analysis',run_number:1,status:'RUNNING',phases:[analyst,counter]}],analysis_runs:[{number:1,status:'RUNNING',steps:[],execution:{status:'ANALYZING',current_role:'counter_analyst',checkpoint:'counter_independent',waiting_reason:'',waiting_causes:[],all_stages_done:false,stages:[{role:'analyst',status:'done'},{role:'counter_analyst',status:'running'},{role:'verifier',status:'waiting'}]}}]};
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language}}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
  await page.route(`**/api/analyses/${id}/progress?*`,route=>route.fulfill({json:{unchanged:true,progress_cursor:value.progress_cursor}}));
  await page.goto(`/analyses/${id}`);
  const block=page.locator('.investigation-progress');
  await expect(block).toHaveCount(1);
  await block.locator(':scope > summary').click();
  await expect(block).toContainText(t('Analyst'));
  await expect(block).toContainText(t('Counter-analyst'));
  await expect(block).toContainText(t('Verifier'));
  const roleTags=block.locator('.investigation-role .connection-role-tag');
  await expect(roleTags).toHaveCount(3);
  expect(await roleTags.evaluateAll(nodes=>nodes.map(node=>node.getAttribute('data-role')))).toEqual(['analyst','counter_analyst','verifier']);
  await expect(block.locator('.work-role-steps')).toHaveCount(2);
  await block.locator('.work-role-steps').last().locator('summary').click();
  await expect(block.locator('[data-work-state="error"]')).toBeVisible();
  await expect(block.locator('[data-work-state="error"] .work-complete')).toHaveCount(0);
  await expect(block.locator('[data-work-state="done"]')).toHaveCount(2);
  await expect(block.getByLabel(translate('{count} operations',language,{count:3}))).toHaveText('× 3');
  await expect(block.locator('[data-work-state="error"]')).toContainText(t('Operation failed'));
  await expect(block.getByText(t('Operation completed'),{exact:true})).toBeVisible();
  await expect(block.getByText(t('Run a command'),{exact:true})).toBeVisible();
  await expect(block.getByText(t('Inspect Git history'),{exact:true})).toBeVisible();
  await expect(block.locator('.work-older')).toHaveCount(0);
  await expect(page.getByLabel(t('Draft response'),{exact:true})).toHaveCount(0);
 });
}
