import {test,expect} from './fixtures';
import {translate} from '../src/lib/i18n';
import type {Page} from '@playwright/test';
import {browserTicketUrl} from '../src/lib/ticket-links';
const at='2026-11-02T12:00:00Z';
const records=[
 {id:'publication-1',title:'Check contract dates',platform:'jira',project:'TEAM',connector_name:'Publishing account',external_id:'14',external_key:'TEAM-14',url:'https://tickets.example/browse/TEAM-14',environment_name:'Staging',published_at:at,request_id:'conversation-one'},
 {id:'publication-2',title:'Clarify calculation',platform:'gitlab',project:'team/app',connector_name:'Other account',external_id:'42',external_key:'#42',url:'https://gitlab.example/team/app/-/issues/42',environment_name:'Production',published_at:at,request_id:'conversation-one'},
];
async function base(page:Page,language='en'){
 await page.route('**/api/**',r=>r.fulfill({json:[]}));
 await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
 await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language}}));
 await page.route('**/api/tickets?*',r=>r.fulfill({json:{items:records,total:2,page:1,page_size:25,environments:['Staging','Production']}}));
}
for(const language of ['en','fr'] as const)for(const theme of ['light','dark']){
 const t=(key:string)=>translate(key,language);
 test(`published history links directly outside without loading drafts or details in ${language} ${theme}`,async({page})=>{
  await base(page,language);const calls:string[]=[];
  page.on('request',request=>{if(request.url().includes('/api/'))calls.push(request.method()+' '+new URL(request.url()).pathname);});
  await page.goto('/tickets');
  await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
  await expect(page.getByRole('heading',{name:t('Published tickets'),exact:true})).toBeVisible();
  const list=page.getByRole('list',{name:t('Published tickets'),exact:true});
  await expect(list.getByRole('listitem')).toHaveCount(2);
  await expect(list).toContainText('TEAM-14');await expect(list).toContainText('#42');
  for(const item of records){
   const row=page.locator(`[data-ticket="${item.id}"]`);
   await expect(row.locator(`[data-provider="${item.platform}"]`)).toBeVisible();
   await expect(row.getByRole('link',{name:t('Open'),exact:true})).toHaveAttribute('href',item.url);
   await expect(row.getByRole('link',{name:t('Open'),exact:true})).toHaveAttribute('target','_blank');
   await expect(row.getByRole('link',{name:item.title,exact:true})).toHaveAttribute('href',item.url);
   await expect(row.getByRole('link',{name:t('Source conversation'),exact:true})).toHaveAttribute('href',`/analyses/${item.request_id}`);
  }
  await expect(page.getByLabel(t('Publication status'),{exact:true})).toHaveCount(0);
  await expect(page.getByTestId('ticket-description')).toHaveCount(0);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button',{name:t('Resume'),exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:t('Next'),exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:t('Refresh'),exact:true}).click();
  await expect(list.getByRole('listitem')).toHaveCount(2);
  expect(calls.every(call=>call.startsWith('GET '))).toBe(true);
  expect(calls.some(call=>/\/api\/tickets\//.test(call))).toBe(false);
  expect(calls.some(call=>/ticket-preparation|\/publications|ticket-connectors/.test(call))).toBe(false);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });
}

test('search and folded filters query only publication history',async({page})=>{
 await base(page);const queries:URLSearchParams[]=[];
 await page.route('**/api/tickets?*',r=>{const query=new URL(r.request().url()).searchParams;queries.push(query);return r.fulfill({json:{items:query.get('search')?[]:records,total:query.get('search')?0:2,page:1,page_size:25,environments:['Staging','Production']}});});
 await page.goto('/tickets');
 await expect(page.locator('[data-ticket]')).toHaveCount(2);
 await expect(page.getByLabel('Platform',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Filters',exact:true}).click();
 await page.getByLabel('Platform',{exact:true}).selectOption('gitlab');
 await page.getByLabel('Environment',{exact:true}).selectOption('Production');
 await page.getByLabel('Search tickets',{exact:true}).fill('missing');
 await expect(page.getByText('No published tickets match these filters.',{exact:true})).toBeVisible();
 expect(Object.fromEntries(queries.at(-1)!)).toEqual({platform:'gitlab',environment:'Production',search:'missing',page:'1'});
});

test('local Docker publication links preserve the ticket route without changing public URLs',async()=>{
 const docker='http://host.docker.internal:9080/front/ticket.form.php?id=2';
 for(const hostname of ['localhost','127.0.0.1','[::1]','spechelper.localhost']){
  const result=new URL(browserTicketUrl(docker,hostname)!);
  expect(result.hostname).toBe(hostname);expect(result.port).toBe('9080');
  expect(result.pathname+result.search).toBe('/front/ticket.form.php?id=2');
 }
 expect(browserTicketUrl(docker,'spechelper.example')).toBeNull();
 expect(browserTicketUrl(docker,'')).toBeNull();
 expect(browserTicketUrl(records[0].url,'localhost')).toBe(records[0].url);
 for(const unsafe of ['javascript:alert(1)','//elsewhere.test/ticket','https://user:secret@example.test/ticket','http://localhost:9080/\\evil','http://localhost:9080/\nticket'])expect(browserTicketUrl(unsafe,'localhost')).toBeNull();
});

test('GLPI Docker links open locally with the platform logo',async({page})=>{
 await base(page);
 const record={...records[0],platform:'glpi',external_id:'2',external_key:'2',url:'http://host.docker.internal:9080/front/ticket.form.php?id=2'};
 await page.route('**/api/tickets?*',r=>r.fulfill({json:{items:[record],total:1,page:1,page_size:25,environments:[]}}));
 await page.goto('/tickets');
 const row=page.locator('[data-ticket="publication-1"]');
 await expect(row.locator('[data-provider="glpi"]')).toBeVisible();
 const link=row.getByRole('link',{name:'Open',exact:true});
 const hostname=new URL(page.url()).hostname;
 await expect(link).toHaveAttribute('href',`http://${hostname}:9080/front/ticket.form.php?id=2`);
 await page.context().route(`http://${hostname}:9080/front/ticket.form.php?id=2`,r=>r.fulfill({contentType:'text/html',body:'<h1>Published GLPI ticket 2</h1>'}));
 const opened=page.waitForEvent('popup');await link.click();
 const popup=await opened;await expect(popup.getByRole('heading',{name:'Published GLPI ticket 2'})).toBeVisible();
});

test('empty history stays compact and loading failures can be refreshed',async({page})=>{
 await base(page);let fail=false;
 await page.route('**/api/tickets?*',r=>r.fulfill(fail?{status:503,json:{detail:'Storage unavailable'}}:{json:{items:[],total:0,page:1,page_size:25,environments:[]}}));
 await page.goto('/tickets');
 await expect(page.getByText('No published tickets yet.',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Filters',exact:true})).toHaveCount(0);
 await expect(page.getByRole('list',{name:'Published tickets',exact:true})).toHaveCount(0);
 fail=true;await page.getByRole('button',{name:'Refresh',exact:true}).click();
 await expect(page.getByRole('alert').filter({hasText:'Storage unavailable'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Refresh',exact:true})).toBeEnabled();
});

test('historical records without safe URLs have no misleading external action',async({page})=>{
 await base(page);
 await page.route('**/api/tickets?*',r=>r.fulfill({json:{items:records.map((item,index)=>({...item,url:index?'javascript:alert(1)':''})),total:2,page:1,page_size:25,environments:[]}}));
 await page.goto('/tickets');
 await expect(page.locator('[data-ticket]')).toHaveCount(2);
 await expect(page.getByRole('link',{name:'Open',exact:true})).toHaveCount(0);
 await expect(page.getByText('External link unavailable',{exact:true})).toHaveCount(2);
});

test('pagination appears only for multiple pages',async({page})=>{
 await base(page);const pages:string[]=[];
 await page.route('**/api/tickets?*',r=>{const pageNumber=new URL(r.request().url()).searchParams.get('page')||'1';pages.push(pageNumber);return r.fulfill({json:{items:records,total:26,page:Number(pageNumber),page_size:25,environments:[]}});});
 await page.goto('/tickets');
 await expect(page.getByRole('button',{name:'Previous',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Next',exact:true}).click();
 await expect.poll(()=>pages.at(-1)).toBe('2');
 await expect(page.getByRole('button',{name:'Next',exact:true})).toBeDisabled();
});
