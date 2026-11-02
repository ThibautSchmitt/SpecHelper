import {test,expect} from './fixtures';
import {translate} from '../src/lib/i18n';
import type {Page} from '@playwright/test';

const at='2026-11-02T12:00:00Z';const id='77777777-7777-4777-8777-777777777777';
const ticketId='88888888-8888-4888-8888-888888888888';
const publication={id:'pub-1',title:'Frozen title',body:'Frozen submitted content',status:'PUBLISHED',platform:'jira',project:'TEAM',connector_name:'Publishing account',external_id:'14',external_key:'TEAM-14',url:'https://tickets.example/14',error:'',created_at:at,updated_at:at,request_id:id,version_number:1};
function draft(){return {id:ticketId,read_only:false,revision:1,discussion_revision:1,source_version:null,source_verified:false,analysis_state:'none',verified_scope:'',limitations:[],has_new_messages:false,scope_choice:'unknown',update_recommended:true,title:'Check dates',body:'## Acceptance criteria\n\nReject invalid dates.',markdown:'# Check dates',publication_available:false,publication_allowed:false,topic_message_id:1,topics:[{id:1,label:'Prevent invalid dates'}],analyses:[],generation:null};}
function record(){return {...publication,id:ticketId,kind:'preparation',conversation_ticket_id:ticketId,title:'Check dates',description:draft().body,status:'DRAFT',platform:'',project:'',connector_name:'',external_id:'',external_key:'',url:'',version_number:null,environment_name:'Staging',conversation_title:'Contract dates',subject:'Prevent invalid dates',topic_message_id:1,publications:[],labels:[],payload_available:true};}
async function base(page:Page,language='en'){
 await page.route('**/api/**',r=>r.fulfill({json:[]}));
 await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
 await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language}}));
 let current:any=record();let saved:any=draft();let reads=0;
 await page.route('**/api/tickets?*',r=>{reads++;return r.fulfill({json:{items:[current],total:1,page:1,page_size:25,environments:['Staging']}});});
 await page.route(`**/api/tickets/${ticketId}`,r=>r.fulfill({json:current}));
 const conversation=()=>({id,title:'Contract dates',need:'Explain dates',status:'DISCUSSING',conversation_state:'DISCUSSION',created_at:at,workflow:'question',messages:[],discussion:{enabled:true,revision:1},conversation_tickets:[{id:ticketId,title:saved.title}]});
 await page.route(`**/api/analyses/${id}`,r=>r.fulfill({json:conversation()}));
 await page.route(`**/api/analyses/${id}/ticket-preparation?*`,r=>r.fulfill({json:saved}));
 await page.route(`**/api/analyses/${id}/ticket-preparation`,r=>{
  const payload=r.request().postDataJSON();saved={...saved,...payload,revision:saved.revision+1};current={...current,title:saved.title,description:saved.body};return r.fulfill({json:saved});
 });
 return {get current(){return current;},set current(value:any){current=value;},get reads(){return reads;}};
}
for(const language of ['en','fr'] as const){
 const t=(key:string)=>translate(key,language);
 test(`compact tickets can be edited in place and reopened without analysis in ${language}`,async({page})=>{
  const fixture=await base(page,language);const writes:string[]=[];
  page.on('request',request=>{if(request.method()!=='GET')writes.push(new URL(request.url()).pathname);});
  await page.goto('/tickets');
  await expect(page.getByRole('heading',{name:t('Tickets'),exact:true})).toBeVisible();
  await expect(page.getByText(t('Drafts and tickets published from your conversations.'),{exact:true})).toBeVisible();
  await expect(page.getByLabel(t('Platform'),{exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:t('Next'),exact:true})).toHaveCount(0);
  await expect(page.getByText(t('No external reference'),{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:t('Resume'),exact:true}).click();
  const dialog=page.getByRole('dialog',{name:t('Prepare a ticket'),exact:true});
  await expect(dialog).toBeVisible();
  expect(new URL(page.url()).pathname).toBe('/tickets');
  await dialog.getByLabel(t('Ticket title'),{exact:true}).fill('Edited correction');
  await dialog.getByLabel(t('Ticket description'),{exact:true}).fill('## Acceptance criteria\n\nKeep the user edits.');
  await dialog.getByRole('button',{name:t('Save'),exact:true}).click();
  await expect(dialog.getByText(t('Ticket draft saved.'),{exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:t('Cancel'),exact:true}).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Edited correction',exact:true})).toBeVisible();
  await page.getByRole('button',{name:t('Resume'),exact:true}).click();
  await expect(page.getByRole('dialog').getByLabel(t('Ticket description'),{exact:true})).toHaveValue('## Acceptance criteria\n\nKeep the user edits.');
  expect(writes).toEqual([`/api/analyses/${id}/ticket-preparation`]);
  expect(fixture.reads).toBeGreaterThan(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });
 test(`publications retain separate outcomes and uncertainty never sends a write in ${language}`,async({page})=>{
  const fixture=await base(page,language);
  fixture.current={...fixture.current,status:'UNCERTAIN',version_number:1,publications:[publication,{...publication,id:'pub-2',status:'UNCERTAIN',platform:'gitlab',connector_name:'Second account',project:'42',url:'',external_id:'',external_key:'',error:'Publication needs checking',attempt_history:[{status:'ERROR',error:'Previous rejection',observed_at:at}]}]};
  const writes:string[]=[];page.on('request',request=>{if(request.method()!=='GET')writes.push(request.url());});
  await page.goto('/tickets');
  const publications=page.getByRole('region',{name:t('Publications'),exact:true});
  await expect(publications).toContainText('TEAM');await expect(publications).toContainText('42');
  await expect(publications.getByText(t('Publication to verify'),{exact:true})).toBeVisible();
  await expect(publications.getByText(t('The external ticket may already exist. Verification will not create another ticket.'),{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:t('Source conversation'),exact:true})).toHaveAttribute('href',`/analyses/${id}#message-1`);
  await expect(publications.getByRole('button',{name:t('Retry'),exact:true})).toHaveCount(0);
  expect(writes).toEqual([]);
 });
}

test('filters are folded, server-backed, and pagination is conditional',async({page})=>{
 await base(page);const queries:URLSearchParams[]=[];
 await page.route('**/api/tickets?*',r=>{const query=new URL(r.request().url()).searchParams;queries.push(query);return r.fulfill({json:{items:query.get('status')==='ERROR'?[]:[record()],total:query.get('status')==='ERROR'?0:1,page:1,page_size:25,environments:['Staging']}});});
 await page.goto('/tickets');await expect(page.getByRole('button',{name:'Check dates',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Filters',exact:true}).click();
 await page.getByLabel('Platform',{exact:true}).selectOption('gitlab');
 await page.getByLabel('Environment',{exact:true}).selectOption('Staging');
 await page.getByLabel('Search tickets',{exact:true}).fill('dates');
 await page.getByLabel('Publication status',{exact:true}).selectOption('ERROR');
 await expect(page.getByText('No tickets match these filters.',{exact:true})).toBeVisible();
 expect(Object.fromEntries(queries.at(-1)!)).toEqual({platform:'gitlab',environment:'Staging',status:'ERROR',search:'dates',page:'1'});
 await expect(page.getByRole('button',{name:'Next',exact:true})).toHaveCount(0);
});

test('empty tickets and failed reads stay compact and truthful',async({page})=>{
 await base(page);let fail=false;
 await page.route('**/api/tickets?*',r=>r.fulfill(fail?{status:503,json:{detail:'Storage unavailable'}}:{json:{items:[],total:0,page:1,page_size:25}}));
 await page.goto('/tickets');await expect(page.getByText('No tickets yet. Tickets prepared from your conversations will appear here.',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Filters',exact:true})).toHaveCount(0);
 fail=true;await page.getByRole('button',{name:'Refresh',exact:true}).click();
 await expect(page.getByRole('alert').filter({hasText:'Storage unavailable'})).toContainText('Storage unavailable');
 await expect(page.getByRole('button',{name:'Refresh',exact:true})).toBeEnabled();
});

test('ticket badges use the existing light and dark theme colors',async({page})=>{
 await base(page);
 const states=['DRAFT','PUBLISHING','PUBLISHED','ERROR','UNCERTAIN'];
 await page.route(/\/api\/tickets\/ticket-\d+$/,r=>r.fulfill({json:{...record(),id:r.request().url().split('/').at(-1)}}));
 await page.route('**/api/tickets?*',r=>r.fulfill({json:{items:states.map((status,index)=>({...record(),id:`ticket-${index}`,status})),total:5,page:1,page_size:25}}));
 await page.goto('/tickets');
 const badges=page.getByRole('list',{name:'Ticket list',exact:true}).locator('.badge');
 await expect(badges).toHaveCount(5);
 for(const theme of ['light','dark']){
  await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
  const colors=await badges.evaluateAll(nodes=>nodes.map((node,index)=>{
   const probe=document.createElement('span');probe.style.color=`var(--${['muted-foreground','running','success','danger','paused'][index]})`;document.body.append(probe);
   const expected=getComputedStyle(probe).color;probe.remove();return {actual:getComputedStyle(node).color,expected};
  }));
  expect(colors.every(value=>value.actual===value.expected)).toBe(true);
 }
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('a legacy destination draft resumes its existing publication editor',async({page})=>{
 const fixture=await base(page);
 fixture.current={...fixture.current,kind:'publication_draft',version_number:1,platform:'gitlab',project:'legacy/project',connector_name:'Legacy account'};
 const writes:string[]=[];page.on('request',request=>{if(request.method()!=='GET')writes.push(request.url());});
 await page.goto('/tickets');
 await expect(page.getByTestId('ticket-description')).toContainText('Reject invalid dates.');
 await page.getByRole('button',{name:'Resume',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Publish ticket',exact:true})).toBeVisible();
 expect(new URL(page.url()).pathname).toBe('/tickets');
 expect(writes).toEqual([]);
});
