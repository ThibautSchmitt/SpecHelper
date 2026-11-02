import {test,expect} from './fixtures';
import {translate} from '../src/lib/i18n';

const id='54545454-5454-4545-8545-545454545454';
const at='2026-11-02T09:00:00Z';
for(const language of ['en','fr'] as const)for(const theme of ['light','dark']){
 const t=(key:string)=>translate(key,language);
 test(`role tags share connection styling and retry resumes the failed cycle in ${language} ${theme}`,async({page})=>{
  let retries=0,otherCalls=0;
  const run={number:1,status:'ERROR',started_at:at,finished_at:at,steps:[],execution:{status:'ERROR',current_role:'analyst',checkpoint:'analyst',all_stages_done:false,stages:[{role:'analyst',status:'error'},{role:'counter_analyst',status:'not_started'},{role:'verifier',status:'not_started'}]}};
  let value:any={id,title:'Benefit behavior',need:'Explain benefits.',workflow:'question',environment_name:'Staging',status:'ERROR',conversation_state:'DISCUSSION',created_at:at,analysis_protocol:'2.4',error:'The AI reached the execution time limit. Completed observations are preserved; retry to resume this step.',
   baseline:[],database:{},attachments:[],progress:[],questions:[],conversation:[],versions:[],latest_version:null,decisions:[],decision_history:[],messages:[{id:1,role:'user',kind:'need',content:'Explain benefits.',created_at:at}],analysis_runs:[run],discussion:{enabled:true,mode:'analysis',revision:1,job:{id:1,status:'DONE',operation:'ticket_preparation'}}};
  await page.route('**/api/**',r=>r.fulfill({json:[]}));
  await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
  await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language}}));
  await page.route('**/api/queue',r=>r.fulfill({json:[{id:22,kind:'analysis',title:'Another analysis',status:'RUNNING',queue_state:'RUNNING',request_status:'ANALYZING',public_role:'counter_analyst',created_at:at,started_at:at,href:'/analyses/another',can_cancel:false,environment_name:'Staging',operation:'Source analysis'}]}));
  await page.route(`**/api/analyses/${id}`,r=>r.fulfill({json:value}));
  await page.route(`**/api/analyses/${id}/discussion`,r=>{otherCalls++;return r.fulfill({json:value});});
  await page.route(`**/api/analyses/${id}/deep-analyze`,r=>{otherCalls++;return r.fulfill({json:value});});
  await page.route(`**/api/questions/${id}/retry`,r=>{
   retries++;value={...value,status:'QUEUED',conversation_state:'IN_PROGRESS',error:'',analysis_runs:[{...run,status:'QUEUED'}]};return r.fulfill({json:value});
  });
  await page.goto(`/analyses/${id}`);
  await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
  await page.locator('.investigation-progress > summary').click();
  const tags=page.locator('.investigation-stages .connection-role-tag');
  await expect(tags).toHaveCount(3);
  const styles=await tags.evaluateAll(nodes=>nodes.map(node=>{
   const style=getComputedStyle(node);return {color:style.color,background:style.backgroundColor,border:style.borderTopWidth,padding:style.padding,fontSize:style.fontSize};
  }));
  expect(new Set(styles.map(style=>style.color)).size).toBe(3);
  expect(styles.every(style=>style.border==='0px' && style.padding==='3px 8px' && style.fontSize==='10px')).toBe(true);
  await expect(page.locator('[data-stage="verifier"]')).toContainText(t('Not started'));
  await page.getByRole('button',{name:t('Activity'),exact:true}).click();
  const activity=page.locator('.queue-card:visible .connection-role-tag').first();
  await expect(activity).toHaveText(t('Counter-analyst'));
  expect(await activity.evaluate(node=>getComputedStyle(node).color)).toBe(styles[1].color);
  const drawer=page.locator('#activity-drawer');
  if(await drawer.isVisible())await drawer.getByRole('button',{name:t('Close'),exact:true}).click();
  else await page.getByRole('button',{name:t('Activity'),exact:true}).click();
  await page.getByRole('button',{name:t('Retry'),exact:true}).click();
  expect(retries).toBe(1);expect(otherCalls).toBe(0);
  await expect(page.getByLabel(t('Your message'),{exact:true})).toBeDisabled();
 });
}
