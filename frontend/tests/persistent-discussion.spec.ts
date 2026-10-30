import {test,expect} from './fixtures';
import {translate} from '../src/lib/i18n';

const id='31313131-3131-4313-8313-313131313131';
const at='2026-10-30T10:00:00Z';
const later='2026-10-30T10:02:00Z';
function dossier(){return {
 id,title:'Benefit behavior',need:'Explain benefit behavior.',original_need:'Explain benefit behavior.',workflow:'question',intent_mode:'auto',environment_name:'Staging',environment_id:1,
 status:'DISCUSSING',result_state:'discussion',created_at:at,analysis_protocol:'2.4',baseline:[],database:{},attachments:[],progress:[],error:'',understanding:'',
 questions:[],conversation:[],latest_version:null,versions:[],decision_revision:0,decisions:[],decision_history:[],validated_version:null,conclusions_stale:false,
 messages:[{id:1,role:'user',kind:'need',content:'Explain benefit behavior.',created_at:at},{id:2,role:'assistant',kind:'discussion_reply',content:'A **discussion** answer.\n\n| Scope | Status |\n| --- | --- |\n| Sources | To check |',created_at:later}],
 discussion:{enabled:true,mode:'discussion',revision:1,has_new_messages:true,connection_id:1,job:{id:1,status:'DONE',created_at:at,error:'',waiting_reason:''}},analysis_runs:[],
};}

for(const language of ['en','fr'] as const){
 const t=(key:string)=>translate(key,language);
 test(`scope clarification returns to single-assistant start in ${language}`,async({page})=>{
  const source=dossier();let starts=0;
  let value:any={...source,status:'DRAFT',scope_revision:1,scope_assessment:{status:'NEEDS_CLARIFICATION',operation:'analyze',message:'Relate this to your project',question:'How does this relate to the selected project or its business context?'},messages:[source.messages[0]],discussion:{...source.discussion,revision:0,job:null}};
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language,primary_color:'#168e95'}}));
  await page.route('**/api/environments',route=>route.fulfill({json:[{id:1,name:'Staging',status:'READY',repositories:[]}]}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
  await page.route(`**/api/questions/${id}/scope`,route=>{value={...value,scope_assessment:{...value.scope_assessment,status:'IN_SCOPE'},scope_revision:2};return route.fulfill({json:value});});
  await page.route(`**/api/analyses/${id}/analyze`,route=>{
   starts++;value={...value,status:'QUEUED',discussion:{...value.discussion,revision:1,job:{id:1,status:'QUEUED',created_at:at,error:'',waiting_reason:''}}};return route.fulfill({json:value});
  });
  await page.goto(`/analyses/${id}`);
  await page.getByLabel(t('How does this relate to the selected project or its business context?'),{exact:true}).fill('It concerns the benefit code.');
  await page.getByRole('button',{name:t('Save project context'),exact:true}).click();
  await page.getByRole('button',{name:t('Start discussion'),exact:true}).click();
  expect(starts).toBe(1);
  await expect(page.locator('.investigation-progress')).toHaveCount(0);
  await expect(page.getByLabel(t('Your message'),{exact:true})).toBeDisabled();
 });
 test(`discussion errors stay localized and offer explicit session recovery in ${language}`,async({page})=>{
  const error='The discussion response failed. Your messages are preserved; retry with a new session.';
  const source=dossier();const value:any={...source,status:'ERROR',error,discussion:{...source.discussion,job:{...source.discussion.job,status:'ERROR',error}}};
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language,primary_color:'#168e95'}}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
  await page.goto(`/analyses/${id}`);
  await expect(page.getByRole('button',{name:t('Resume with a new session'),exact:true})).toBeVisible();
  await expect(page.locator('[role="alert"]').filter({hasText:t(error)})).toHaveText(t(error));
  await expect(page.locator('.investigation-progress')).toHaveCount(0);
 });
 test(`configuration change offers explicit restart with the unsent message in ${language}`,async({page})=>{
  let value:any=dossier();let attempts=0;
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language,primary_color:'#168e95'}}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
  await page.route(`**/api/analyses/${id}/discussion`,route=>{
   const body=route.request().postDataJSON();attempts++;
   if(attempts===1)return route.fulfill({status:409,json:{detail:'The selected AI configuration changed. Start a new discussion session explicitly.'}});
   expect(body).toEqual({message:'Please clarify.',expected_revision:1,restart_session:true});
   value={...value,status:'QUEUED',discussion:{...value.discussion,revision:2,job:{...value.discussion.job,status:'QUEUED'}}};
   return route.fulfill({json:value});
  });
  await page.goto(`/analyses/${id}`);
  await page.getByLabel(t('Your message'),{exact:true}).fill('Please clarify.');
  await page.getByRole('button',{name:t('Send message'),exact:true}).click();
  await expect(page.getByLabel(t('Your message'),{exact:true})).toHaveValue('Please clarify.');
  await page.getByRole('button',{name:t('Resume with a new session'),exact:true}).click();
  expect(attempts).toBe(2);
 });
 test(`single conversation continues after reload and deep analysis in ${language}`,async({page})=>{
  let value:any=dossier();let turns=0,deep=0;
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language,primary_color:'#168e95'}}));
  await page.route('**/api/ai-connections',route=>route.fulfill({json:[{id:1,name:'ChatGPT',agent:'codex',model:'fixture-model',enabled:true,roles:['analyst','counter_analyst','verifier']}]}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
  await page.route(`**/api/analyses/${id}/discussion`,async route=>{
   const body=route.request().postDataJSON();expect(body.expected_revision).toBe(value.discussion.revision);expect(body).not.toHaveProperty('expected_version');
   turns++;
   value={...value,status:'QUEUED',result_state:'queued',messages:[...value.messages,{id:10+turns,role:'user',kind:'discussion',content:body.message,created_at:later}],discussion:{...value.discussion,mode:'discussion',revision:value.discussion.revision+1,has_new_messages:true,job:{id:2,status:'RUNNING',created_at:later,error:'',waiting_reason:''}}};
   await route.fulfill({json:value});
  });
  await page.route(`**/api/analyses/${id}/deep-analyze`,async route=>{
   expect(route.request().postDataJSON()).toEqual({expected_revision:2,intent:'auto'});deep++;
   value={...value,status:'ANALYZING',discussion:{...value.discussion,mode:'analysis',has_new_messages:false},analysis_runs:[{number:1,status:'RUNNING',steps:[],execution:{status:'ANALYZING',current_role:'analyst',checkpoint:'analyst',waiting_reason:'',waiting_causes:[],all_stages_done:false,stages:[{role:'analyst',status:'running'},{role:'counter_analyst',status:'waiting'},{role:'verifier',status:'waiting'}]}}]};
   await route.fulfill({json:value});
  });
  await page.goto(`/analyses/${id}`);
  await expect(page.locator('.conversation-assistant header strong')).toHaveText('Team Assistant');
  await expect(page.locator('.conversation-answer table')).toBeVisible();
  await expect(page.locator('.investigation-progress')).toHaveCount(0);
  await expect(page.locator('#analysis-report')).toHaveCount(0);
  await page.getByLabel(t('Your message'),{exact:true}).fill('Explain that exception.');
  await expect(page.getByRole('button',{name:t('Launch deep analysis'),exact:true})).toBeDisabled();
  await page.getByRole('button',{name:t('Send message'),exact:true}).click();
  await expect(page.getByLabel(t('Your message'),{exact:true})).toBeDisabled();
  expect(turns).toBe(1);expect(deep).toBe(0);
  value={...value,status:'DISCUSSING',result_state:'discussion',messages:[...value.messages,{id:20,role:'assistant',kind:'discussion_reply',content:'The exception needs a source check.',created_at:later}],discussion:{...value.discussion,job:{...value.discussion.job,status:'DONE'}}};
  await expect(page.getByText('The exception needs a source check.',{exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByText('The exception needs a source check.',{exact:true})).toBeVisible();
  expect(turns).toBe(1);expect(deep).toBe(0);
  await page.getByRole('button',{name:t('Launch deep analysis'),exact:true}).click();
  await expect(page.locator('.investigation-progress')).toHaveCount(1);
  const version={id:'version',number:1,status:'PARTIAL',format_version:'2.9',language,created_at:'2026-10-30T10:04:00Z',run_number:1,explanation:{title:'Benefit conditions',summary:'The source defines an exception. Database behavior remains unverified.'},ticket:{},markdown:'Detailed findings',goal_markdown:'',evidence:{claims:[],blocking:true,limitations:['Database behavior remains unverified.'],database:{status:'not_configured',limitations:[],checks:[],scope:''}}};
  value={...value,status:'PARTIAL',latest_version:version,versions:[{number:1,status:'PARTIAL',created_at:version.created_at}],analysis_runs:[{...value.analysis_runs[0],status:'PARTIAL',execution:{...value.analysis_runs[0].execution,status:'PARTIAL',all_stages_done:true,stages:['analyst','counter_analyst','verifier'].map(role=>({role,status:'done'}))}}]};
  const result=page.locator('[data-message="result-1"]');
  await expect(result).toContainText('Database behavior remains unverified.');
  await expect(result).toContainText(t('Some conclusions remain unverified. See the analysis report for the limits and evidence.'));
  await page.getByLabel(t('Your message'),{exact:true}).fill('Explain the result more simply.');
  await page.getByRole('button',{name:t('Send message'),exact:true}).click();
  expect(turns).toBe(2);expect(deep).toBe(1);
  await expect(result).toContainText('Database behavior remains unverified.');
  await expect(page.getByText(t('New messages are not covered by the previous analysis.'),{exact:true})).toBeVisible();
  await expect(page.locator('.investigation-progress')).toHaveCount(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });

 test(`ticket request requires explicit deep launch and cancellation preserves input in ${language}`,async({page})=>{
  let value:any=dossier();let launches=0;
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language,primary_color:'#168e95'}}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
  await page.route(`**/api/analyses/${id}/deep-analyze`,route=>{
   expect(route.request().postDataJSON()).toEqual({expected_revision:1,intent:'change'});launches++;
   value={...value,workflow:'request',status:'QUEUED',discussion:{...value.discussion,mode:'analysis'}};
   return route.fulfill({json:value});
  });
  await page.route(`**/api/analyses/${id}/cancel`,route=>{value={...value,status:'CANCELLED'};return route.fulfill({json:value});});
  await page.goto(`/analyses/${id}`);
  await expect(page.locator('#analysis-report')).toHaveCount(0);
  await page.getByRole('button',{name:t('Prepare a ticket'),exact:true}).click();
  expect(launches).toBe(1);
  await page.getByRole('button',{name:t('Cancel'),exact:true}).click();
  await expect(page.getByLabel(t('Your message'),{exact:true})).toBeEnabled();
  await expect(page.getByText('Explain benefit behavior.',{exact:true})).toBeVisible();
 });
}
