import {test,expect} from './fixtures';
import {translate} from '../src/lib/i18n';

const id='45454545-4545-4545-8545-454545454545';
const at='2026-11-02T10:00:00Z';
function conversation(){return {
 id,title:'Benefit management',need:'Explain dates',workflow:'question',environment_id:1,environment_name:'Staging',status:'PARTIAL',conversation_state:'DISCUSSION',conversation_incident:false,
 created_at:at,latest_activity_at:at,analysis_protocol:'2.4',baseline:[],database:{},attachments:[],progress:[],error:'',understanding:'',
 questions:[],conversation:[],latest_version:null,versions:[],decision_revision:0,decisions:[],decision_history:[],validated_version:null,
 messages:[{id:1,role:'user',kind:'need',content:'Explain dates',created_at:at},{id:2,role:'assistant',kind:'discussion_reply',content:'Dates explanation',created_at:at},{id:3,role:'user',kind:'discussion',content:'Explain rounding',created_at:at}],
 discussion:{enabled:true,mode:'discussion',revision:2,connection_id:1,job:null},analysis_runs:[],conversation_tickets:[],
};}

for(const language of ['en','fr'] as const){
 const t=(key:string)=>translate(key,language);
 test(`conversation states and archive filter use only the four public states in ${language}`,async({page})=>{
  await page.route('**/api/**',r=>r.fulfill({json:[]}));
  await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language}}));
  await page.route('**/api/environments',r=>r.fulfill({json:[]}));
  await page.route(/\/api\/analyses(?:\?.*)?$/,r=>{
   const archived=new URL(r.request().url()).searchParams.get('archived')==='archived';
   return r.fulfill({json:{items:[{...conversation(),href:`/analyses/${id}`,title:archived?'Archived subject':'Benefit management',archived_at:archived?at:null}],total:1,page:1,page_size:20}});
  });
  await page.goto('/analyses');
  await expect(page.locator('.analysis-row')).toContainText(t('In discussion'));
  await expect(page.getByLabel(t('Status'),{exact:true}).locator('option')).toHaveCount(5);
  await page.getByLabel(t('Archive filter'),{exact:true}).selectOption('archived');
  await expect(page.locator('.analysis-row')).toContainText('Archived subject');
  await expect(page.locator('.analysis-row')).toContainText(t('Archived'));
 });

 test(`deep analysis requires explicit scoped confirmation and archive is reversible in ${language}`,async({page})=>{
  let value:any=conversation(),deep=0;
  await page.route('**/api/**',r=>r.fulfill({json:[]}));
  await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language}}));
  await page.route(`**/api/analyses/${id}`,r=>r.fulfill({json:value}));
  await page.route(`**/api/analyses/${id}/archive`,r=>{value={...value,archived_at:r.request().postDataJSON().archived?at:null};return r.fulfill({json:value});});
  await page.route(`**/api/analyses/${id}/deep-analyze`,r=>{
   expect(r.request().postDataJSON()).toMatchObject({subject:'Explain rounding',message_ids:[3],topic_message_id:3,expected_revision:2});
   deep++;return r.fulfill({json:{...value,conversation_state:'IN_PROGRESS',status:'QUEUED'}});
  });
  await page.goto(`/analyses/${id}`);
  await page.getByRole('button',{name:t('Archive'),exact:true}).click();
  await expect(page.getByLabel(t('Your message'),{exact:true})).toBeDisabled();
  await page.reload();
  await expect(page.getByRole('button',{name:t('Unarchive'),exact:true})).toBeVisible();
  await page.getByRole('button',{name:t('Unarchive'),exact:true}).click();
  await expect(page.getByLabel(t('Your message'),{exact:true})).toBeEnabled();
  await page.getByRole('button',{name:t('Launch deep analysis'),exact:true}).click();
  const modal=page.getByRole('dialog',{name:t('Deep analysis scope'),exact:true});
  await expect(modal.getByLabel(t('Need to investigate'),{exact:true})).toHaveValue('Explain rounding');
  await expect(modal.getByRole('checkbox',{name:'Explain rounding',exact:true})).toBeChecked();
  await expect(modal.getByRole('checkbox',{name:'Explain dates',exact:true})).not.toBeChecked();
  expect(deep).toBe(0);
  await modal.getByRole('button',{name:t('Launch deep analysis'),exact:true}).click();
  await expect(modal).not.toBeVisible();expect(deep).toBe(1);
 });

 test(`two analysis results prepare separate tickets without triggering an analysis in ${language}`,async({page})=>{
  let value:any={...conversation(),versions:[{number:1,status:'PARTIAL',created_at:at,subject:'Dates'},{number:2,status:'PARTIAL',created_at:at,subject:'Rounding'}]},deep=0,saves=0;
  await page.route('**/api/**',r=>r.fulfill({json:[]}));
  await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language}}));
  await page.route(`**/api/analyses/${id}`,r=>r.fulfill({json:value}));
  await page.route(`**/api/analyses/${id}/deep-analyze`,r=>{deep++;return r.fulfill({json:value});});
  await page.route(new RegExp(`/api/analyses/${id}/ticket-preparation(?:\\?.*)?$`),r=>{
   const source=Number(new URL(r.request().url()).searchParams.get('source_version'))||null;
   let draft:any={id:null,revision:0,discussion_revision:2,source_version:source,source_verified:false,analysis_state:source?'partial':'none',verified_scope:source===1?'Dates':'Rounding',limitations:[],has_new_messages:false,scope_choice:'unknown',title:source===1?'Dates ticket':'Rounding ticket',body:source===1?'DATES_PROOF':'ROUNDING_PROOF',publication_available:false,publication_allowed:false,topic_message_id:source===1?1:3,analyses:[{number:1,subject:'Dates',status:'PARTIAL'},{number:2,subject:'Rounding',status:'PARTIAL'}],topics:[]};
   if(r.request().method()==='PUT'){
    const body=r.request().postDataJSON();saves++;
    expect(body.new_ticket).toBe(true);expect(body.source_version).toBe(saves);
    draft={...draft,...body,id:`ticket-${saves}`,revision:1};
    value={...value,conversation_tickets:[...value.conversation_tickets,{id:draft.id,title:draft.title,source_version:body.source_version,status:'DRAFT',created_at:at}]};
   }
   return r.fulfill({json:draft});
  });
  await page.goto(`/analyses/${id}`);
  const actions=page.getByRole('button',{name:t('Prepare a ticket'),exact:true});
  await expect(actions).toHaveCount(3);
  for(const n of [1,2]){
   await actions.nth(n-1).click();
   const modal=page.getByRole('dialog',{name:t('Prepare a ticket'),exact:true});
   await expect(modal.locator("select")).toHaveCount(0);
   await expect(modal.getByLabel(t('Ticket description'),{exact:true})).toHaveValue(n===1?'DATES_PROOF':'ROUNDING_PROOF');
   await modal.getByRole('button',{name:t('Save'),exact:true}).click();
   await expect(modal.getByText(t('Ticket draft saved.'),{exact:true})).toBeVisible();
   await modal.getByRole('button',{name:t('Cancel'),exact:true}).click();
  }
  expect(deep).toBe(0);expect(saves).toBe(2);
  await expect(page.getByRole('button',{name:t('Open ticket draft'),exact:true})).toHaveCount(2);
 });
}
