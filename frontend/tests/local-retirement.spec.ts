import {test,expect} from './fixtures';
import {translate} from '../src/lib/i18n';

const id='45454545-4545-4545-8545-454545454545';
const at='2026-11-07T10:00:00Z';
for(const language of ['en','fr'] as const){
 const t=(key:string)=>translate(key,language);
 test(`remove one publication locally after confirmation in ${language}`,async({page})=>{
  let removed=false, writes=0;
  await page.route('**/api/**',r=>r.fulfill({json:[]}));
  await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language}}));
  const row=(n:number)=>({id:String(n),title:'External ticket '+n,platform:'gitlab',project:'team/test',connector_name:'Test GitLab',external_key:'#'+n,url:`https://gitlab.example/team/test/-/issues/${n}`,environment_name:'Staging',published_at:at,request_id:id});
  await page.route(/\/api\/tickets(?:\?.*)?$/,r=>r.fulfill({json:{items:removed?[row(2)]:[row(1),row(2)],total:removed?1:2,page:1,page_size:25,environments:['Staging']}}));
  await page.route('**/api/tickets/1',r=>{expect(r.request().method()).toBe('DELETE');expect(r.request().postDataJSON()).toEqual({confirmed:true});writes++;removed=true;return r.fulfill({json:{status:'REMOVED'}});});
  await page.goto('/tickets');
  const open=page.locator('[data-ticket="1"]').getByRole('link',{name:language==='fr'?'Ouvrir':'Open',exact:true});
  await expect(open).toBeVisible();
  await expect(open).toHaveAttribute('href','https://gitlab.example/team/test/-/issues/1');
  await expect(open).toHaveAttribute('target','_blank');
  await page.locator('[data-ticket="1"] summary').click();
  await page.getByRole('button',{name:t('Remove from SpecHelper'),exact:true}).click();
  const modal=page.getByRole('dialog',{name:t('Remove from SpecHelper'),exact:true});
  await expect(modal).toContainText(t('Remove this ticket from SpecHelper? It will remain available on its external platform.'));
  expect(writes).toBe(0);
  await modal.getByRole('button',{name:t('Cancel'),exact:true}).click();
  expect(writes).toBe(0);
  await page.locator('[data-ticket="1"] summary').click();
  await page.getByRole('button',{name:t('Remove from SpecHelper'),exact:true}).click();
  await modal.getByRole('button',{name:t('Confirm deletion'),exact:true}).click();
  await expect(page.locator('[data-ticket="1"]')).toHaveCount(0);
  await expect(page.locator('[data-ticket="2"]')).toBeVisible();
  expect(writes).toBe(1);
  await expect(page.locator('[data-ticket="2"] a').first()).toHaveAttribute('href','https://gitlab.example/team/test/-/issues/2');
  await page.evaluate(()=>document.documentElement.classList.add('dark'));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });

 test(`delete one analysis waits for session cleanup and retains the conversation in ${language}`,async({page})=>{
  let deleted=false,calls=0;
  const run=(number:number)=>({number,status:'CANCELLED',steps:[],started_at:at,finished_at:at});
  const value=()=>({id,title:'Dates',need:'Explain dates',workflow:'question',environment_id:1,environment_name:'Staging',status:'DISCUSSING',conversation_state:'DISCUSSION',created_at:at,analysis_protocol:'2.4',baseline:[],database:{},attachments:[],progress:[],error:'',understanding:'',questions:[],conversation:[],latest_version:null,versions:[],decision_revision:0,decisions:[],decision_history:[],validated_version:null,messages:[{id:1,role:'user',kind:'need',content:'Independent conversation message',created_at:at}],discussion:{enabled:true,mode:'discussion',revision:0,connection_id:1,job:null},analysis_runs:deleted?[run(2)]:[run(1),run(2)],conversation_tickets:[]});
  await page.route('**/api/**',r=>r.fulfill({json:[]}));
  await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language}}));
  await page.route(`**/api/analyses/${id}`,r=>r.fulfill({json:value()}));
  await page.route(`**/api/analyses/${id}/runs/1`,r=>{expect(r.request().postDataJSON()).toEqual({confirmed:true});calls++;if(calls>1)deleted=true;return r.fulfill({json:{status:deleted?'DELETED':'STOPPING'}});});
  await page.goto(`/analyses/${id}`);
  await page.locator('[data-message="progress-1"]').getByLabel(t('Analysis actions'),{exact:true}).click();
  await page.locator('[data-message="progress-1"]').getByRole('button',{name:t('Delete deep analysis'),exact:true}).click();
  const modal=page.getByRole('dialog',{name:t('Delete deep analysis'),exact:true});
  expect(calls).toBe(0);
  await modal.getByRole('button',{name:t('Confirm deletion'),exact:true}).click();
  await expect(modal.getByRole('status')).toContainText(t('Stopping agents and releasing their sessions…'));
  await expect(modal).not.toBeVisible({timeout:10000});
  await expect(page.locator('[data-message="progress-1"]')).toHaveCount(0);
  await expect(page.locator('[data-message="progress-2"]')).toBeVisible();
  await expect(page.getByText('Independent conversation message',{exact:true})).toBeVisible();
  expect(calls).toBe(2);
 });
}

test('analysis preparation without a persisted cycle does not offer a broken deletion action',async({page})=>{
 await page.route('**/api/**',r=>r.fulfill({json:[]}));
 await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
 await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language:'en'}}));
 await page.route(`**/api/analyses/${id}`,r=>r.fulfill({json:{id,title:'Preparing analysis',need:'Explain dates',workflow:'question',environment_id:1,environment_name:'Staging',status:'ANALYZING',conversation_state:'IN_PROGRESS',created_at:at,analysis_protocol:'2.4',baseline:[],database:{},attachments:[],progress:[],error:'',questions:[],conversation:[],latest_version:null,versions:[],decision_revision:0,decisions:[],decision_history:[],validated_version:null,messages:[{id:1,role:'user',kind:'need',content:'Explain dates',created_at:at}],discussion:{enabled:true,mode:'analysis',revision:0,connection_id:1,job:null},analysis_runs:[],conversation_tickets:[]}}));
 await page.goto(`/analyses/${id}`);
 await expect(page.locator('[data-message="progress-pending"]')).toBeVisible();
 await expect(page.getByLabel('Analysis actions',{exact:true})).toHaveCount(0);
});
