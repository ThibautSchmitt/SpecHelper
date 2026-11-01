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
  await expect(page.getByRole('button',{name:t('Retry'),exact:true})).toBeVisible();
  await expect(page.locator('[role="alert"]').filter({hasText:t(error)})).toHaveText(t(error));
  await expect(page.locator('.investigation-progress')).toHaveCount(0);
 });
 test(`confirmed stale replies remain identifiable without replaying their content in ${language}`,async({page})=>{
  const error='The assistant returned a previous response without completing this turn. Retry; your messages are preserved.';
  const source=dossier();const value:any={...source,status:'ERROR',error,messages:[...source.messages,
   {id:3,role:'assistant',kind:'discussion_reply',content:'CACHED_STALE_REPLY',created_at:later,data:{response_status:'stale'}},
  ],discussion:{...source.discussion,job:{...source.discussion.job,status:'ERROR',error}}};
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language}}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
  await page.goto(`/analyses/${id}`);
  await expect(page.locator('[data-message="message-3"]')).toContainText(t('Response interrupted'));
  await expect(page.locator('[data-message="message-2"]')).toContainText('A discussion answer.');
  await expect(page.locator('.analysis-conversation')).not.toContainText('CACHED_STALE_REPLY');
  await expect(page.getByRole('button',{name:t('Retry'),exact:true})).toBeVisible();
  await expect(page.locator('[role="alert"]').filter({hasText:t(error)})).toHaveText(t(error));
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
  await page.getByRole('button',{name:t('Retry'),exact:true}).click();
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
   const body=route.request().postDataJSON();expect(body.expected_revision).toBe(value.discussion.revision);expect(body).not.toHaveProperty('expected_version');expect(body).not.toHaveProperty('connection_id');
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
  await expect(page.locator('.conversation-assistant header')).toHaveCount(0);
  await expect(page.getByRole('button',{name:t('Change assistant'),exact:true})).toHaveCount(0);
  await expect(page.locator('#discussion-assistant')).toHaveCount(0);
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

 test(`ticket preparation opens a saved draft before an explicit deep launch in ${language}`,async({page})=>{
  let value:any=dossier();let launches=0;
  let draft:any={revision:0,discussion_revision:1,source_version:null,source_verified:false,analysis_state:'none',verified_scope:'',limitations:[],has_new_messages:false,scope_choice:'unknown',update_recommended:true,title:'Contract dates',body:'Prevent inconsistent dates.',markdown:'# Contract dates\n\n> Unverified draft\n\nPrevent inconsistent dates.',publication_available:false,publication_allowed:false};
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language,primary_color:'#168e95'}}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
  await page.route(`**/api/analyses/${id}/ticket-preparation`,route=>{
   if(route.request().method()==='PUT'){
    const payload=route.request().postDataJSON();expect(payload.expected_revision).toBe(draft.revision);
    draft={...draft,revision:draft.revision+1,title:payload.title,body:payload.body};
   }
   return route.fulfill({json:draft});
  });
  await page.route(`**/api/analyses/${id}/deep-analyze`,route=>{
   expect(route.request().postDataJSON()).toEqual({expected_revision:1,intent:'change',preparation_revision:1});launches++;
   value={...value,workflow:'request',status:'QUEUED',discussion:{...value.discussion,mode:'analysis'}};
   return route.fulfill({json:value});
  });
  await page.route(`**/api/analyses/${id}/cancel`,route=>{value={...value,status:'CANCELLED'};return route.fulfill({json:value});});
  await page.goto(`/analyses/${id}`);
  await expect(page.locator('#analysis-report')).toHaveCount(0);
  await page.getByRole('button',{name:t('Prepare a ticket'),exact:true}).click();
  const preparation=page.getByRole('dialog',{name:t('Prepare a ticket'),exact:true});
  await expect(preparation).toBeVisible();
  await expect(preparation).toContainText(t('No deep analysis yet.'));
  expect(launches).toBe(0);
  await preparation.getByLabel(t('Ticket description'),{exact:true}).fill('Reject inconsistent dates with a message.');
  await preparation.getByRole('button',{name:t('Save'),exact:true}).click();
  await expect(preparation).toContainText(t('Ticket draft saved.'));
  expect(launches).toBe(0);
  await preparation.getByRole('button',{name:t('Cancel'),exact:true}).click();
  await page.reload();
  await page.getByRole('button',{name:t('Prepare a ticket'),exact:true}).click();
  await expect(preparation.getByLabel(t('Ticket description'),{exact:true})).toHaveValue('Reject inconsistent dates with a message.');
  await preparation.getByRole('button',{name:t('Launch deep analysis'),exact:true}).click();
  expect(launches).toBe(1);
  await expect(preparation).not.toBeVisible();
  await page.locator('.conversation-reply').getByRole('button',{name:t('Cancel'),exact:true}).click();
  await expect(page.getByLabel(t('Your message'),{exact:true})).toBeEnabled();
  await expect(page.getByText('Explain benefit behavior.',{exact:true})).toBeVisible();
 });

 test(`ticket drafting selects one subject and uses one assistant without deep analysis in ${language}`,async({page})=>{
  let value:any=dossier();let generations=0,deep=0,polls=0;
  let draft:any={revision:0,discussion_revision:1,source_version:null,source_verified:false,analysis_state:'interrupted',verified_scope:'',limitations:[],has_new_messages:true,scope_choice:'unknown',title:'Switch question',body:'Recorded switch findings in `menu.py:42`.',markdown:'Unverified draft',publication_available:false,publication_allowed:false,topic_message_id:2,topics:[{id:2,label:'Explain the switch menu.'},{id:1,label:'Explain import batches.'}],discussion_findings_available:true,generation:null};
  await page.route('**/api/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language}}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
  await page.route(`**/api/analyses/${id}/deep-analyze`,route=>{deep++;return route.fulfill({json:value});});
  await page.route(new RegExp(`/api/analyses/${id}/ticket-preparation(?:\\?.*)?$`),route=>{
   const topic=new URL(route.request().url()).searchParams.get('topic_message_id');
   if(topic==='1')draft={...draft,topic_message_id:1,title:'Import batches',body:'Recorded batch findings in `import.py:12`.'};
   if(route.request().method()==='PUT'){const payload=route.request().postDataJSON();draft={...draft,revision:draft.revision+1,title:payload.title,body:payload.body,topic_message_id:payload.topic_message_id};}
   if(draft.generation?.status==='RUNNING'&&++polls>=2){draft={...draft,revision:draft.revision+1,title:'Document import validation',body:'## Findings\nThe import validates the file (`import.py:12`).\n\n## Limits\nNot independently verified.',generation:{...draft.generation,status:'DONE'}};value={...value,status:'DISCUSSING'};}
   return route.fulfill({json:draft});
  });
  await page.route(`**/api/analyses/${id}/ticket-preparation/generate`,route=>{
   expect(route.request().postDataJSON()).toMatchObject({topic_message_id:1,expected_revision:1});generations++;
   draft={...draft,generation:{id:9,status:'RUNNING',error:'',waiting_reason:''}};value={...value,status:'QUEUED'};
   return route.fulfill({json:value});
  });
  await page.goto(`/analyses/${id}`);
  await page.getByRole('button',{name:t('Prepare a ticket'),exact:true}).click();
  const dialog=page.getByRole('dialog',{name:t('Prepare a ticket'),exact:true});
  await expect(dialog.getByLabel(t('Ticket subject'),{exact:true})).toHaveValue('2');
  await dialog.getByLabel(t('Ticket subject'),{exact:true}).selectOption('1');
  await expect(dialog.getByLabel(t('Ticket description'),{exact:true})).toHaveValue('Recorded batch findings in `import.py:12`.');
  expect(generations).toBe(0);expect(deep).toBe(0);
  await dialog.getByRole('button',{name:t('Write from conversation'),exact:true}).click();
  await expect(dialog.getByLabel(t('Ticket description'),{exact:true})).toBeDisabled();
  await expect(dialog.getByLabel(t('Ticket title'),{exact:true})).toHaveValue('Document import validation');
  await expect(dialog.getByLabel(t('Ticket description'),{exact:true})).toContainText('import.py:12');
  expect(generations).toBe(1);expect(deep).toBe(0);
 });

 for(const state of ['complete','partial','interrupted'] as const){
  test(`ticket preparation reuses ${state} analysis without relaunching in ${language}`,async({page})=>{
   const source=dossier();let launches=0;
   const value:any={...source,status:state==='complete'?'DISCUSSING':state==='partial'?'PARTIAL':'ERROR'};
   let draft:any={revision:0,discussion_revision:1,source_version:1,source_verified:state==='complete',analysis_state:state,verified_scope:'Explain the cause of inconsistent dates.',limitations:state==='partial'?['Runtime checks were not completed.']:[],has_new_messages:true,scope_choice:'unknown',update_recommended:true,title:'Reject inconsistent dates',body:'## Findings\n\nIndependent date updates.\n\n## Additional request — unverified\n\nShow an error.',markdown:'Unverified proposals',publication_available:false,publication_allowed:false};
   await page.route('**/api/**',route=>route.fulfill({json:[]}));
   await page.route('**/api/access/session',route=>route.fulfill({json:{authenticated:true,mode:'local'}}));
   await page.route('**/api/settings',route=>route.fulfill({json:{name:'Team Assistant',language}}));
   await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
   await page.route(`**/api/analyses/${id}/deep-analyze`,route=>{launches++;return route.fulfill({json:value});});
   await page.route(`**/api/analyses/${id}/ticket-preparation`,route=>{
    if(route.request().method()==='PUT'){const payload=route.request().postDataJSON();draft={...draft,revision:1,scope_choice:payload.scope_choice};}
    return route.fulfill({json:draft});
   });
   await page.goto(`/analyses/${id}`);
   await page.getByRole('button',{name:t('Prepare a ticket'),exact:true}).click();
   const preparation=page.getByRole('dialog',{name:t('Prepare a ticket'),exact:true});
   await expect(preparation.getByLabel(t('Ticket description'),{exact:true})).toContainText('Show an error.');
   await preparation.getByLabel(t('Changes since the analysis'),{exact:true}).selectOption('clarified');
   await preparation.getByRole('button',{name:t('Save'),exact:true}).click();
   await expect(preparation).toContainText(t('Ticket draft saved.'));
   await expect(preparation.getByRole('button',{name:t('Update analysis'),exact:true})).toBeVisible();
   expect(launches).toBe(0);
  });
 }
}
