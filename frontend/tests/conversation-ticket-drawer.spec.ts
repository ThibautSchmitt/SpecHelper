import {test,expect} from './fixtures';
import {translate} from '../src/lib/i18n';
import type {Page} from '@playwright/test';
const id='67676767-6767-4767-8767-676767676767';
const ticket='68686868-6868-4868-8868-686868686868';
const at='2026-11-02T12:00:00Z';
const body='## Need\n\nReject invalid periods.\n\n## Acceptance criteria\n\n- Invalid periods are rejected.';
async function setup(page:Page,language:'en'|'fr',outcome='PUBLISHED'){
 let draft:any={id:null,read_only:false,revision:0,discussion_revision:3,source_version:null,source_verified:false,scope_choice:'unknown',title:'Reject invalid periods',body,markdown:body,topic_message_id:100,anchor_message_id:101,limitations:[],generation:null};
 let value:any={id,title:'Contract behavior',need:'Explore contract behavior',workflow:'question',environment_name:'Staging',status:'DISCUSSING',conversation_state:'DISCUSSION',created_at:at,analysis_protocol:'2.4',baseline:[],database:{},attachments:[],progress:[],questions:[],conversation:[],versions:[],latest_version:null,decisions:[],decision_history:[],analysis_runs:[],publications:[],conversation_tickets:[],work_progress:[],
  messages:[...Array.from({length:40},(_,index)=>({id:index+1,role:index%2?'assistant':'user',kind:index%2?'discussion_reply':'discussion',content:`OTHER_SUBJECT_${index}`,created_at:at})),{id:100,role:'user',kind:'discussion',content:'Prevent invalid periods.',created_at:at},{id:101,role:'assistant',kind:'discussion_reply',content:'The period needs validation before saving.',created_at:at},{id:102,role:'user',kind:'discussion',content:'Unrelated question about exports.',created_at:at},{id:103,role:'assistant',kind:'discussion_reply',content:'The export is configured separately.',created_at:at}],discussion:{enabled:true,mode:'discussion',revision:3,job:null}};
 let generations=0,deep=0;const posts:any[]=[];let attempts:any[]=[];
 await page.route('**/api/**',r=>r.fulfill({json:[]}));
 await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
 await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language}}));
 await page.route(`**/api/analyses/${id}`,r=>r.fulfill({json:value}));
 await page.route(`**/api/analyses/${id}/progress?*`,r=>r.fulfill({json:{unchanged:true}}));
 await page.route(`**/api/analyses/${id}/deep-analyze`,r=>{deep++;return r.fulfill({json:value});});
 await page.route(`**/api/analyses/${id}/ticket-preparation?*`,r=>{
  const query=new URL(r.request().url()).searchParams;
  if(!query.has('ticket_id'))expect(query.get('anchor_message_id')).toBe('101');
  return r.fulfill({json:draft});
 });
 await page.route(`**/api/analyses/${id}/ticket-preparation`,r=>{
  const payload=r.request().postDataJSON();expect(payload.anchor_message_id).toBe(101);
  draft={...draft,...payload,id:ticket,revision:draft.revision+1};value={...value,conversation_tickets:[{id:ticket,title:draft.title,status:'DRAFT',created_at:at}]};return r.fulfill({json:draft});
 });
 await page.route(`**/api/analyses/${id}/ticket-preparation/generate`,r=>{
  const payload=r.request().postDataJSON();expect(payload.anchor_message_id).toBe(101);generations++;
  draft={...draft,title:'Reject invalid periods',body,markdown:body,revision:draft.revision+1};return r.fulfill({json:value});
 });
 await page.route(`**/api/ticket-connectors?*`,r=>r.fulfill({json:[{id:4,name:'Selected account',platform:'jira',enabled:true,status:'CONNECTED',projects:[],default_project:''}]}));
 await page.route('**/api/ticket-connectors/4/projects',r=>r.fulfill({json:[{id:'TEAM',name:'Team project'}]}));
 const endpoint=`/api/analyses/${id}/tickets/${ticket}`;
 await page.route(`**${endpoint}/publications*`,r=>{
  if(r.request().method()==='GET')return r.fulfill({json:attempts});
  const payload=r.request().postDataJSON();posts.push(payload);
  expect(payload.confirmed).toBe(true);expect(payload.unverified_confirmed).toBe(true);expect(payload.title).toBe(draft.title);
  const publication={id:'publication-1',connector_id:4,project:'TEAM',idempotency_key:payload.idempotency_key,snapshot:{...payload,conversation_ticket_revision:1,version_id:null,baseline:[],selected_attachments:[]},title:payload.title,status:outcome,url:outcome==='PUBLISHED'?'https://jira.example.test/browse/TEAM-14':'',platform:'jira',external_key:'TEAM-14',created_at:at};
  value={...value,publications:[publication]};attempts=[publication];
  return r.fulfill({json:{...publication,error:outcome==='ERROR'?'Provider rejected the ticket':outcome==='UNCERTAIN'?'Publication requires verification':'',attachment_delivery:[]}});
 });
 let target:any={draft_id:'destination-draft',draft_revision:1,title:'Reject invalid periods',body,ticket_format:'standard',requires_unverified_confirmation:true,
   publication_allowed:true,publication_blockers:[],template_id:'',issue_type:'',fields:[],values:{},labels:[],assignees:[],templates:[],issue_types:[],defaults:{},revision:'options',options_revision:'options',format:'markdown',available_attachments:[],selected_attachments:[]};
 await page.route(`**${endpoint}/publication-draft*`,r=>{
  if(r.request().method()==='PUT'){
   const {fields,...payload}=r.request().postDataJSON();
   target={...target,...payload,values:fields,draft_revision:target.draft_revision+1};
  }
  else target={...target,title:draft.title};
  return r.fulfill({json:target});
 });
 return {get generations(){return generations;},get deep(){return deep;},posts,archive(){value={...value,archived_at:at};}};
}
for(const language of ['en','fr'] as const)for(const theme of ['light','dark']){
 const t=(key:string)=>translate(key,language);
 test(`selected answer prepares a small persistent drawer and publishes after confirmation in ${language} ${theme}`,async({page})=>{
  const fixture=await setup(page,language);
  await page.goto(`/analyses/${id}`);await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
  const message=page.locator('[data-message="message-101"]');
  await message.getByLabel(t('Message actions'),{exact:true}).click();
  await message.getByRole('button',{name:t('Prepare a ticket'),exact:true}).click();
  const drawer=page.getByRole('dialog',{name:t('Prepare a ticket'),exact:true});
  await expect(drawer).toHaveClass(/skill-drawer/);
  await expect.poll(()=>fixture.generations).toBe(1);
  await expect(drawer.getByLabel(t('Ticket description'),{exact:true})).toHaveValue(body);
  await expect(drawer.locator('select')).toHaveCount(0);
  await expect(drawer.getByText(t('Not independently verified'),{exact:true})).toBeVisible();
  await drawer.getByLabel(t('Ticket title'),{exact:true}).fill('Edited correction');
  await drawer.getByRole('button',{name:t('Save'),exact:true}).click();
  await expect(drawer.getByText(t('Ticket draft saved.'),{exact:true})).toBeVisible();
  await drawer.getByRole('button',{name:t('Close'),exact:true}).click();
  await page.locator(`[data-message="ticket-${ticket}"]`).getByRole('button',{name:t('Open ticket draft'),exact:true}).click();
  await expect(drawer.getByLabel(t('Ticket title'),{exact:true})).toHaveValue('Edited correction');
  expect(fixture.generations).toBe(1);
  await drawer.getByRole('button',{name:t('Continue to publication'),exact:true}).click();
  const publication=page.getByRole('dialog',{name:t('Publish ticket'),exact:true});
  await publication.getByLabel(t('Publication connection'),{exact:true}).selectOption('4');
  await publication.getByLabel(t('Project / repository'),{exact:true}).selectOption('TEAM');
  await expect(publication.getByLabel(t('Ticket description'),{exact:true})).toHaveValue(body);
  await publication.getByRole('button',{name:t('Create ticket'),exact:true}).click();
  const confirmation=page.getByRole('alertdialog',{name:t('Publish without independent verification'),exact:true});
  await expect(confirmation).toBeInViewport();expect(fixture.posts).toHaveLength(0);expect(fixture.deep).toBe(0);
  await confirmation.getByRole('button',{name:t('Publish anyway'),exact:true}).click();
  await expect.poll(()=>fixture.posts.length).toBe(1);
  await publication.getByRole('button',{name:t('Close'),exact:true}).first().click();
  await drawer.getByRole('button',{name:t('Close'),exact:true}).click();
  const event=page.locator('[data-message="publication-publication-1"]');
  await expect(event.getByRole('link')).toHaveAttribute('href','https://jira.example.test/browse/TEAM-14');
  await expect(event).toContainText('TEAM-14');
  await page.reload();await expect(event).toHaveCount(1);
  fixture.archive();await page.reload();await expect(event).toHaveCount(1);
  expect(fixture.deep).toBe(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });
}

for(const outcome of ['ERROR','UNCERTAIN'])test(`a ${outcome} write keeps the draft and never adds a success link`,async({page})=>{
 const t=(key:string)=>translate(key,'fr');
 const fixture=await setup(page,'fr',outcome);
 await page.goto(`/analyses/${id}`);
 const message=page.locator('[data-message="message-101"]');
 await message.getByLabel(t('Message actions'),{exact:true}).click();
 await message.getByRole('button',{name:t('Prepare a ticket'),exact:true}).click();
 const drawer=page.getByRole('dialog',{name:t('Prepare a ticket'),exact:true});
 await expect.poll(()=>fixture.generations).toBe(1);
 await drawer.getByRole('button',{name:t('Continue to publication'),exact:true}).click();
 const publication=page.getByRole('dialog',{name:t('Publish ticket'),exact:true});
 await publication.getByLabel(t('Publication connection'),{exact:true}).selectOption('4');
 await publication.getByLabel(t('Project / repository'),{exact:true}).selectOption('TEAM');
 await publication.getByRole('button',{name:t('Create ticket'),exact:true}).click();
 await page.getByRole('alertdialog').getByRole('button',{name:t('Publish anyway'),exact:true}).click();
 await expect.poll(()=>fixture.posts.length).toBe(1);
 await publication.getByRole('button',{name:t('Close'),exact:true}).first().click();
 await drawer.getByRole('button',{name:t('Close'),exact:true}).click();
 await page.reload();
 await expect(page.getByRole('link',{name:t('Open published ticket'),exact:true})).toHaveCount(0);
 await page.locator(`[data-message="ticket-${ticket}"]`).getByRole('button',{name:t('Open ticket draft'),exact:true}).click();
 await expect(drawer.getByLabel(t('Ticket description'),{exact:true})).toHaveValue(body);
 expect(fixture.generations).toBe(1);
 if(outcome==='UNCERTAIN'){
  await drawer.getByRole('button',{name:t('Continue to publication'),exact:true}).click();
  await publication.getByRole('button',{name:t('Verify publication'),exact:true}).click();
  await expect.poll(()=>fixture.posts.length).toBe(2);
  expect(fixture.posts[1].idempotency_key).toBe(fixture.posts[0].idempotency_key);
  expect(fixture.posts[1]).not.toHaveProperty('conversation_ticket_revision');
  expect(fixture.posts[1]).not.toHaveProperty('selected_attachments');
 }
 expect(fixture.deep).toBe(0);
});
