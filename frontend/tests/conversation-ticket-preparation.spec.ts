import {test,expect} from './fixtures';
import {translate} from '../src/lib/i18n';
import type {Page} from '@playwright/test';
const id='67676767-6767-4767-8767-676767676767';
const ticket='68686868-6868-4868-8868-686868686868';
const at='2026-11-03T09:00:00Z';
const body='## Need\n\nRound contributions after aggregation.\n\n## Acceptance criteria\n\n- Adjustments are included.';

async function setup(page:Page,language:'en'|'fr',seeded=false,outcome='PUBLISHED') {
 let draft:any={id:seeded?ticket:null,active:seeded,read_only:false,revision:seeded?1:0,discussion_revision:3,source_version:null,source_verified:false,scope_choice:'unknown',title:seeded?'Contribution rounding':'',body:seeded?body:'',markdown:seeded?body:'',initial_pending:false,proposal:null,generation:null};
 let value:any={id,title:'Contribution rules',need:'Clarify contribution rounding',workflow:'question',environment_name:'Staging',status:'DISCUSSING',conversation_state:'DISCUSSION',created_at:at,analysis_protocol:'2.4',baseline:[],database:{},attachments:[],progress:[],questions:[],conversation:[],versions:[],latest_version:null,decisions:[],decision_history:[],analysis_runs:[],publications:[],work_progress:[],
  messages:Array.from({length:80},(_,index)=>({id:index+1,role:index%2?'assistant':'user',kind:index%2?'discussion_reply':'discussion',content:`OTHER_SUBJECT_${index}`,created_at:at})),discussion:{enabled:true,mode:'discussion',revision:3,job:null},
  // Compatibility records must never become a list of draft cards.
  conversation_tickets:[{id:'old-draft',title:'Historical draft',active:false,created_at:at}],active_ticket:seeded?{id:ticket,title:draft.title,status:'DRAFT'}:null};
 let generations=0,deep=0,pendingReads=0,failNext=false,failSave=false;
 const destinationSaves:any[]=[];
 const posts:any[]=[];const generated:any[]=[];const documentRequests:any[]=[];let attempts:any[]=[];
 function setActive(){value={...value,active_ticket:draft.id?{id:draft.id,title:draft.title,status:'DRAFT'}:null};}
 await page.route('**/api/**',r=>r.fulfill({json:[]}));
 await page.route('**/api/access/session',r=>r.fulfill({json:{authenticated:true,mode:'local'}}));
 await page.route('**/api/settings',r=>r.fulfill({json:{name:'SpecHelper',language}}));
 await page.route(`**/api/analyses/${id}`,r=>r.fulfill({json:value}));
 await page.route(`**/api/analyses/${id}/progress?*`,r=>r.fulfill({json:{unchanged:true}}));
 await page.route(`**/api/analyses/${id}/deep-analyze`,r=>{deep++;return r.fulfill({json:value});});
 const prep=`/api/analyses/${id}/ticket-preparation`;
 await page.route(new RegExp(`${prep}(?:\\?.*)?$`),r=>{
  if(r.request().method()==='PUT'){
   if(failSave){failSave=false;return r.fulfill({status:503,json:{detail:'Draft could not be saved.'}});}
   const payload=r.request().postDataJSON();
   expect(payload.expected_revision).toBe(draft.revision);
   draft={...draft,...payload,revision:draft.revision+1,markdown:payload.body,proposal:null};setActive();
  }else if(draft.generation?.status==='QUEUED'&&++pendingReads>=2){
   draft={...draft,title:'Contribution rounding',body,markdown:body,initial_pending:false,generation:{...draft.generation,status:'DONE'}};setActive();
  }
  return r.fulfill({json:draft});
 });
 await page.route(`**${prep}/generate`,r=>{
  const payload=r.request().postDataJSON();generated.push(payload);generations++;
  if(failNext){failNext=false;return r.fulfill({status:503,json:{detail:'The selected assistant is unavailable.'}});}
  if(payload.purpose==='prepare'){
   pendingReads=0;draft={...draft,id:ticket,active:true,initial_pending:true,generation:{id:generations,status:'QUEUED',error:'',waiting_reason:''}};setActive();
  }else if(payload.purpose==='replace'){
   expect(payload.replace_confirmed).toBe(true);draft={...draft,title:'Export contracts',body:'Export active contracts only.',revision:draft.revision+1,proposal:null};setActive();
  }else draft={...draft,proposal:{id:'69696969-6969-4969-8969-696969696969',title:'Contribution rounding',body:'Round the total including the new contribution rule.'}};
  return r.fulfill({json:value});
 });
 await page.route(`**${prep}/proposal`,r=>{
  const payload=r.request().postDataJSON();expect(payload.expected_revision).toBe(draft.revision);
  if(payload.apply)draft={...draft,title:draft.proposal.title,body:draft.proposal.body,markdown:draft.proposal.body,revision:draft.revision+1};
  draft={...draft,proposal:null};setActive();return r.fulfill({json:draft});
 });
 await page.route('**/api/ticket-connectors?*',r=>r.fulfill({json:[{id:4,name:'Selected account',platform:'jira',enabled:true,status:'CONNECTED',projects:[],default_project:''}]}));
 await page.route('**/api/ticket-connectors/4/projects',r=>r.fulfill({json:[{id:'TEAM',name:'Team project'}]}));
 const endpoint=`/api/analyses/${id}/tickets/${ticket}`;
 await page.route(`**${endpoint}/publications*`,r=>{
  if(r.request().method()==='GET')return r.fulfill({json:attempts});
  const payload=r.request().postDataJSON();posts.push(payload);
  expect(payload.confirmed).toBe(true);expect(payload.unverified_confirmed).toBe(target.requires_unverified_confirmation);
  const publication={id:'publication-1',connector_id:4,project:'TEAM',idempotency_key:payload.idempotency_key,snapshot:{...payload,conversation_ticket_revision:1,version_id:null,baseline:[],selected_attachments:[]},title:payload.title,status:outcome,url:outcome==='PUBLISHED'?'https://jira.example.test/browse/TEAM-14':'',platform:'jira',external_key:'TEAM-14',created_at:at};
  value={...value,publications:[publication]};attempts=[publication];
  if(outcome==='PUBLISHED'){
   draft={...draft,id:null,active:false,revision:0,title:'',body:'',proposal:null};setActive();
  }else if(outcome==='UNCERTAIN')draft={...draft,read_only:true,can_recover_publication:true};
  return r.fulfill({json:{...publication,error:outcome==='ERROR'?'Provider rejected the ticket':outcome==='UNCERTAIN'?'Publication requires verification':'',attachment_delivery:[]}});
 });
 let target:any={draft_id:'destination-draft',draft_revision:1,title:'',body:'',ticket_format:'standard',requires_unverified_confirmation:true,document_attachment_policy:{enabled:true,max_bytes:25000000},
  publication_allowed:true,publication_blockers:[],template_id:'',issue_type:'',fields:[],values:{},labels:[],assignees:[],templates:[],issue_types:[],defaults:{},revision:'options',options_revision:'options',format:'markdown',available_attachments:[],selected_attachments:[]};
 await page.route(`**${endpoint}/publication-draft*`,r=>{
  if(r.request().method()==='PUT'){
   const data=r.request().postDataJSON();destinationSaves.push(data);
   for(const key of ['id','revision','discussion_revision','source_verified','documents','markdown','proposal','generation'])expect(data).not.toHaveProperty(key);
   const {fields,labels,assignees,...payload}=data;
   target={...target,...payload,values:fields,defaults:{...target.defaults,labels,assignees},draft_revision:target.draft_revision+1};
  }else target={...target,title:draft.title,body:draft.body};
  return r.fulfill({json:target});
 });
 await page.route(`**${endpoint}/documents/generate`,r=>{
  const payload=r.request().postDataJSON();documentRequests.push(payload);
  expect(posts).toHaveLength(0);
  return r.fulfill({json:{status:'DONE',documents:Object.fromEntries(payload.documents.map((kind:string)=>[kind,{name:kind+'.md',generation_id:55}]))}});
 });
 const reportReads:string[]=[];
 await page.route(`**/api/analyses/${id}/versions/1/reports/*`,r=>{
  const kind=r.request().url().split('/').at(-1)!;reportReads.push(kind);
  return r.fulfill({json:{name:`analysis-1-${kind}.md`,content:`# ${kind==='business'?'Functional conclusions':'Technical observations'}\n\n${kind==='business'?'Keep adjustments.':'Inspect \`rounding.py\`.'}\n\n## Limits\n\nImport not checked.`}});
 });
 await page.route(`**/api/analyses/${id}/goal?*`,r=>r.fulfill({json:{name:'goal.md',content:`# Goal\n\n${draft.title}\n\n${draft.body}\n\nWithout deep verification`}}));
 await page.route(`**/api/analyses/${id}/goal/generate?*`,r=>r.fulfill({json:{generation_id:55,status:'QUEUED'}}));
 return {get generations(){return generations;},get deep(){return deep;},posts,generated,reportReads,documentRequests,destinationSaves,
  failSave(){failSave=true;}, options(options:any){target={...target,...options};},
  unsupportedFiles(){target.document_attachment_policy.enabled=false;},
  publications(items:any[]){value={...value,publications:items};},
  verifiedPublication(){target.requires_unverified_confirmation=false;},
  finishAnalysis(){
   const result={id:'result-1',number:1,run_number:1,status:'PARTIAL',created_at:at,workflow:'request',language:'en',artifacts:{},ticket:{title:'Contribution rounding'},markdown:'Partial findings.',goal_markdown:'',evidence:{blocking:true,claims:[],limitations:['Import not checked.']}};
   value={...value,latest_version:result,versions:[result],analysis_runs:[{number:1,status:'PARTIAL',steps:[],started_at:at,finished_at:at}],conversation_state:'DISCUSSION'};
  },fail(){failNext=true;},archive(){value={...value,archived_at:at};}};
}

test('published conversation links use the browser host and show every platform logo',async({page})=>{
 const fixture=await setup(page,'fr');
 const urls={glpi:'http://host.docker.internal:9080/front/ticket.form.php?id=2',gitlab:'https://gitlab.example/team/app/-/issues/42',jira:'https://jira.example/browse/TEAM-14',github:'https://github.com/team/app/issues/3'};
 fixture.publications(Object.entries(urls).map(([platform,url])=>({id:platform,platform,url,status:'PUBLISHED',title:`Published ${platform}`,external_key:'2',created_at:at})));
 await page.goto(`/analyses/${id}`);
 for(const [platform,url] of Object.entries(urls)){
  const event=page.locator(`[data-message="publication-${platform}"]`);
  await expect(event.locator(`[data-provider="${platform}"]`)).toBeVisible();
  await expect(event.getByRole('link',{name:'Ouvrir le ticket publié'})).toHaveAttribute('href',platform==='glpi'?`http://${new URL(page.url()).hostname}:9080/front/ticket.form.php?id=2`:url);
 }
 await page.reload();await expect(page.locator('[data-message="publication-glpi"]')).toHaveCount(1);
 expect(fixture.posts).toHaveLength(0);expect(fixture.generations).toBe(0);expect(fixture.deep).toBe(0);
});

for(const language of ['en','fr'] as const)for(const theme of ['light','dark']){
 const t=(key:string)=>translate(key,language);
 test(`one centered ticket modal prepares updates and publishes in ${language} ${theme}`,async({page},info)=>{
  const fixture=await setup(page,language);
  await page.addInitScript(theme=>localStorage.setItem('spechelper-theme',theme),theme);
  await page.goto(`/analyses/${id}`);await expect(page.locator('html')).toHaveAttribute('data-theme',theme);
  await page.getByRole('button',{name:t('Prepare a ticket'),exact:true}).last().click();
  const modal=page.getByRole('dialog',{name:t('Create ticket'),exact:true});
  await expect(modal).toHaveClass(/ticket-preparation-modal/);
  await expect(modal.getByText(t('Preparing the ticket…'),{exact:true})).toBeVisible();
  await modal.getByRole('button',{name:t('Edit'),exact:true}).click();
  await expect(modal.getByLabel(t('Description'),{exact:true})).toHaveValue(body);
  await expect(modal.getByLabel(t('Publication connection'),{exact:true})).toBeVisible();
  if(language==='fr'){await expect(modal.getByLabel('Titre',{exact:true})).toBeVisible();await expect(modal.getByRole('button',{name:'Publier',exact:true})).toBeVisible();}
  const box=(await modal.boundingBox())!;
  expect(Math.abs(box.x+box.width/2-page.viewportSize()!.width/2)).toBeLessThan(3);
  await modal.getByLabel(t('Title'),{exact:true}).fill('My correction');
  await modal.getByRole('button',{name:t('Save'),exact:true}).click();
  await modal.getByRole('button',{name:t('Close'),exact:true}).first().click();
  await expect(page.locator('[data-message^="ticket-"]')).toHaveCount(0);
  await page.getByRole('button',{name:t('Draft'),exact:true}).click();
  await expect(modal.getByLabel(t('Title'),{exact:true})).toHaveValue('My correction');
  expect(fixture.generations).toBe(1);
  await modal.getByRole('button',{name:t('Improve with AI'),exact:true}).click();
  await modal.getByRole('button',{name:t('Edit'),exact:true}).click();
  await expect(modal.getByLabel(t('Description'),{exact:true})).toHaveValue('Round the total including the new contribution rule.');
  await modal.getByRole('button',{name:t('Keep my draft'),exact:true}).click();
  await expect(modal.getByLabel(t('Title'),{exact:true})).toHaveValue('My correction');
  await modal.getByRole('button',{name:t('Improve with AI'),exact:true}).click();
  if(language==='fr')await expect(modal.getByRole('button',{name:'Appliquer',exact:true})).toBeVisible();
  await modal.getByRole('button',{name:t('Apply'),exact:true}).click();
  await expect(modal.getByLabel(t('Description'),{exact:true})).toHaveValue('Round the total including the new contribution rule.');
  await modal.screenshot({path:`../.local/ticket-ui/${language}-${theme}-${info.project.name}-prepare.png`});
  const publication=page.getByRole('dialog',{name:t('Create ticket'),exact:true});
  await expect(page.locator('dialog[open]')).toHaveCount(1);
  await publication.getByLabel(t('Publication connection'),{exact:true}).selectOption('4');
  await publication.getByLabel(t('Project / repository'),{exact:true}).selectOption('TEAM');
  await publication.screenshot({path:`../.local/ticket-ui/${language}-${theme}-${info.project.name}-publish.png`});
  await publication.getByRole('button',{name:t('Publish'),exact:true}).click();
  await expect(publication.getByLabel(t('Ticket description'),{exact:true})).toHaveCount(0);
  await expect(publication.getByRole('button',{name:t('Reload saved draft'),exact:true})).toHaveCount(0);
  const confirmation=page.getByRole('alertdialog');
  await expect(confirmation).toBeInViewport();expect(fixture.posts).toHaveLength(0);expect(fixture.deep).toBe(0);
  await confirmation.getByRole('button',{name:t('Publish anyway'),exact:true}).click();
  await expect(page.locator('dialog[open]')).toHaveCount(0);
  const link=page.getByRole('link',{name:t('Open published ticket'),exact:true});
  await expect(link).toHaveAttribute('href','https://jira.example.test/browse/TEAM-14');
  await expect(page.locator('[data-message="publication-publication-1"] [data-provider="jira"]')).toBeVisible();
  await page.reload();await expect(link).toHaveCount(1);
  await expect(page.getByRole('button',{name:t('Draft'),exact:true})).toHaveCount(0);
  fixture.archive();await page.reload();await expect(link).toHaveCount(1);
  expect(fixture.deep).toBe(0);expect(fixture.generated.map(item=>item.purpose)).toEqual(['prepare','refresh','refresh']);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });
}

test('existing draft requires an explicit choice to replace and failed refresh keeps manual text',async({page})=>{
 const fixture=await setup(page,'en',true);
 await page.goto(`/analyses/${id}`);
 await page.getByRole('button',{name:'Prepare a ticket',exact:true}).last().click();
 const modal=page.getByRole('dialog',{name:'Create ticket',exact:true});
 await expect(modal.getByText(/A draft already exists/)).toBeVisible();expect(fixture.generations).toBe(0);
 await modal.getByRole('button',{name:'Resume draft',exact:true}).click();
 await modal.getByRole('button',{name:'Edit',exact:true}).click();
 await expect(modal.getByLabel('Description',{exact:true})).toHaveValue(body);
 fixture.fail();await modal.getByRole('button',{name:'Improve with AI',exact:true}).click();
 await expect(modal.getByRole('alert')).toBeVisible();await expect(modal.getByLabel('Description',{exact:true})).toHaveValue(body);
 await modal.getByRole('button',{name:'Close',exact:true}).first().click();
 await page.getByRole('button',{name:'Prepare a ticket',exact:true}).last().click();
 fixture.fail();await modal.getByRole('button',{name:'Replace draft',exact:true}).click();
 await expect(modal.getByRole('alert')).toBeVisible();
 await modal.getByRole('button',{name:'Edit',exact:true}).click();
 await expect(modal.getByLabel('Description',{exact:true})).toHaveValue(body);
 await modal.getByRole('button',{name:'Retry',exact:true}).click();
 await expect(modal.getByLabel('Title',{exact:true})).toHaveValue('Export contracts');
 expect(fixture.generated.at(-1).replace_confirmed).toBe(true);expect(fixture.deep).toBe(0);
});

test('closing saves manual edits and reopening keeps the same draft',async({page})=>{
 await setup(page,'en',true);await page.goto(`/analyses/${id}`);
 await page.getByRole('button',{name:'Draft',exact:true}).click();
 const modal=page.getByRole('dialog',{name:'Create ticket',exact:true});
 await modal.getByLabel('Title',{exact:true}).fill('Unsaved correction');
 await modal.getByRole('button',{name:'Close',exact:true}).first().click();
 await expect(modal).not.toBeVisible();
 await page.getByRole('button',{name:'Draft',exact:true}).click();
 await expect(modal.getByLabel('Title',{exact:true})).toHaveValue('Unsaved correction');
});

for(const outcome of ['ERROR','UNCERTAIN'])test(`a ${outcome} write keeps the draft and never adds a success link`,async({page})=>{
 const fixture=await setup(page,'en',true,outcome);await page.goto(`/analyses/${id}`);
 await page.getByRole('button',{name:'Draft',exact:true}).click();
 const modal=page.getByRole('dialog',{name:'Create ticket',exact:true});
 const publication=page.getByRole('dialog',{name:'Create ticket',exact:true});
 await publication.getByLabel('Publication connection',{exact:true}).selectOption('4');
 await publication.getByLabel('Project / repository',{exact:true}).selectOption('TEAM');
 await publication.getByRole('button',{name:'Publish',exact:true}).click();
 await page.getByRole('alertdialog').getByRole('button',{name:'Publish anyway',exact:true}).click();
 await expect.poll(()=>fixture.posts.length).toBe(1);
 await publication.getByRole('button',{name:'Close',exact:true}).first().click();
 await page.getByRole('button',{name:'Draft',exact:true}).click();
  await modal.getByRole('button',{name:'Edit',exact:true}).click();
 await expect(modal.getByLabel('Description',{exact:true})).toHaveValue(body);
 await modal.getByRole('button',{name:'Close',exact:true}).first().click();await page.reload();
 await expect(page.getByRole('link',{name:'Open published ticket',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Draft',exact:true}).click();
  await modal.getByRole('button',{name:'Edit',exact:true}).click();
 await expect(modal.getByLabel('Description',{exact:true})).toHaveValue(body);expect(fixture.generations).toBe(0);
 if(outcome==='UNCERTAIN'){
  await publication.getByRole('button',{name:'Verify publication',exact:true}).click();
  await expect.poll(()=>fixture.posts.length).toBe(2);
  expect(fixture.posts[1].idempotency_key).toBe(fixture.posts[0].idempotency_key);
  expect(fixture.posts[1]).not.toHaveProperty('conversation_ticket_revision');
 }
 expect(fixture.deep).toBe(0);
});

test('saved draft survives explicit deep analysis, reports and a reviewed update',async({page})=>{
 const fixture=await setup(page,'en',true);await page.goto(`/analyses/${id}`);
 await page.getByRole('button',{name:'Draft',exact:true}).click();
 const draft=page.getByRole('dialog',{name:'Create ticket',exact:true});
 await draft.getByLabel('Title',{exact:true}).fill('Keep manual rounding rules');
 await draft.getByText('Additional options',{exact:true}).click();
 await draft.getByRole('button',{name:'Launch deep analysis',exact:true}).click();
 const scope=page.getByRole('dialog',{name:'Deep analysis',exact:true});
 await expect(scope.getByLabel('Need to analyze',{exact:true})).toHaveValue('Keep manual rounding rules');
 expect(fixture.deep).toBe(0);
 await scope.getByLabel('Need to analyze',{exact:true}).fill('Check rounding and adjustments in imports.');
 await scope.getByRole('button',{name:'Launch deep analysis',exact:true}).click();
 await expect(scope).not.toBeVisible();expect(fixture.deep).toBe(1);
 fixture.finishAnalysis();await page.reload();
 await page.getByRole('button',{name:'View business report',exact:true}).click();
 const business=page.getByRole('dialog',{name:'Business report',exact:true});
 await expect(business.getByRole('heading',{name:'Functional conclusions'})).toBeVisible();
 await expect(business).toContainText('Import not checked.');
 const download=page.waitForEvent('download');await business.getByRole('button',{name:/Download/}).click();
 expect((await download).suggestedFilename()).toBe('analysis-1-business.md');
 await business.getByRole('button',{name:'Close',exact:true}).click();
 await page.getByRole('button',{name:'View technical report',exact:true}).click();
 const technical=page.getByRole('dialog',{name:'Technical report',exact:true});
 await expect(technical.locator('code')).toContainText('rounding.py');
 await technical.getByRole('button',{name:'Close',exact:true}).click();
 await page.getByRole('button',{name:'Draft',exact:true}).click();
 await expect(draft.getByLabel('Title',{exact:true})).toHaveValue('Keep manual rounding rules');
 await draft.getByRole('button',{name:'Improve with AI',exact:true}).click();
 await draft.getByRole('button',{name:'Apply',exact:true}).click();
 await expect(draft.getByLabel('Title',{exact:true})).toHaveValue('Contribution rounding');
 expect(fixture.deep).toBe(1);expect(fixture.reportReads).toEqual(['business','technical']);
});

test('documents are optional, retained with manual edits and generated only at publication',async({page})=>{
 const fixture=await setup(page,'fr',true);await page.goto(`/analyses/${id}`);
 await page.getByRole('button',{name:translate('Draft','fr'),exact:true}).click();
 const draft=page.getByRole('dialog',{name:translate('Create ticket','fr'),exact:true});
 await draft.getByLabel('Titre',{exact:true}).fill('Ma règle métier corrigée');
 await expect(page.getByRole('button',{name:'Générer goal.md',exact:true})).toHaveCount(0);
 await expect(draft.getByLabel(/^goal.md/)).toBeChecked();
 await draft.getByLabel(/^Rapport métier/).check();
 await expect(draft.getByLabel(/^Rapport technique/)).not.toBeChecked();
 expect(fixture.documentRequests).toHaveLength(0);
 await draft.getByRole('button',{name:'Enregistrer',exact:true}).click();
 await expect(draft.getByRole('button',{name:'Enregistrer',exact:true})).toBeDisabled();
 expect(fixture.deep).toBe(0);expect(fixture.generations).toBe(0);
 const publication=page.getByRole('dialog',{name:translate('Create ticket','fr'),exact:true});
 await publication.getByLabel('Connexion de publication',{exact:true}).selectOption('4');
 await publication.getByLabel('Projet / dépôt',{exact:true}).selectOption('TEAM');
 expect(fixture.documentRequests).toHaveLength(0);
 await publication.getByRole('button',{name:'Publier',exact:true}).click();
 await expect.poll(()=>fixture.documentRequests.length).toBe(1);
 expect(fixture.posts).toHaveLength(0);
 await publication.getByRole('button',{name:translate('Publish anyway','fr'),exact:true}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 expect(fixture.documentRequests[0].documents).toEqual(['goal','business']);
 expect(fixture.posts[0].document_generations).toEqual({goal:55,business:55});
 expect(fixture.posts[0].title).toBe('Ma règle métier corrigée');
});

test('document failure allows an explicit writer choice and never publishes before success',async({page})=>{
 const fixture=await setup(page,'fr',true);let selected:string|null=null;
 await page.route(`**/api/analyses/${id}/tickets/${ticket}/documents/generate`,r=>{
  selected=String(r.request().postDataJSON().connection_id||'');
  return r.fulfill(selected==='1'?{json:{status:'DONE',documents:{goal:{generation_id:55}}}}:{status:409,json:{detail:'Choose an AI connection allowed to act as analyst.'}});
 });
 await page.route(`**/api/analyses/${id}/goal/assistants`,r=>r.fulfill({json:[{connection_id:1,name:'ChatGPT',agent:'codex',model:'gpt-5.6-luna'}]}));
 await page.goto(`/analyses/${id}`);await page.getByRole('button',{name:translate('Draft','fr'),exact:true}).click();
 const publication=page.getByRole('dialog',{name:translate('Create ticket','fr'),exact:true});
 await publication.getByLabel(translate('Publication connection','fr'),{exact:true}).selectOption('4');
 await publication.getByLabel(translate('Project / repository','fr'),{exact:true}).selectOption('TEAM');
 await publication.getByRole('button',{name:'Publier',exact:true}).click();
 await expect(publication.getByLabel('IA de rédaction')).toBeVisible();
 expect(fixture.posts).toHaveLength(0);
 await publication.getByLabel('IA de rédaction').selectOption('1');
 await publication.getByRole('button',{name:'Réessayer',exact:true}).click();
 await publication.getByRole('button',{name:translate('Publish anyway','fr'),exact:true}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 expect(selected).toBe('1');expect(fixture.deep).toBe(0);expect(fixture.posts).toHaveLength(1);
});

test('unsupported destinations require deselecting documents and use no AI',async({page})=>{
 const fixture=await setup(page,'en',true);fixture.unsupportedFiles();
 await page.goto(`/analyses/${id}`);await page.getByRole('button',{name:'Draft',exact:true}).click();
 const publication=page.getByRole('dialog',{name:'Create ticket',exact:true});
 await publication.getByLabel('Publication connection',{exact:true}).selectOption('4');
 await publication.getByLabel('Project / repository',{exact:true}).selectOption('TEAM');
 await expect(publication.getByRole('button',{name:'Publish',exact:true})).toBeDisabled();
 await expect(publication).toContainText('This destination cannot receive generated documents.');
 await publication.getByLabel('goal.md',{exact:true}).uncheck();
 await publication.getByRole('button',{name:'Publish',exact:true}).click();
 await publication.getByRole('button',{name:'Publish anyway',exact:true}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 expect(fixture.documentRequests).toHaveLength(0);expect(fixture.posts).toHaveLength(1);
});

test('closing while documents are generated never starts an external publication',async({page})=>{
 const fixture=await setup(page,'en',true);let started=false;
 await page.route(`**/api/analyses/${id}/tickets/${ticket}/documents/generate`,r=>{started=true;return r.fulfill({json:{generation_id:55,status:'QUEUED',documents:{}}});});
 await page.route(`**/api/analyses/${id}/tickets/${ticket}/documents/55`,r=>r.fulfill({json:{generation_id:55,status:'RUNNING',documents:{}}}));
 await page.goto(`/analyses/${id}`);await page.getByRole('button',{name:'Draft',exact:true}).click();
 const publication=page.getByRole('dialog',{name:'Create ticket',exact:true});
 await publication.getByLabel('Publication connection',{exact:true}).selectOption('4');
 await publication.getByLabel('Project / repository',{exact:true}).selectOption('TEAM');
 await publication.getByRole('button',{name:'Publish',exact:true}).click();
 await expect(publication.getByText('Generating selected documents…',{exact:true})).toBeVisible();
 expect(started).toBe(true);expect(fixture.posts).toHaveLength(0);
 await publication.getByRole('button',{name:'Close',exact:true}).first().click();
 await expect(page.getByRole('dialog',{name:'Create ticket',exact:true})).not.toBeVisible();
 expect(fixture.posts).toHaveLength(0);expect(fixture.deep).toBe(0);
});

test('verified publication also requires confirmation without a repeated preview',async({page})=>{
 const fixture=await setup(page,'en',true);fixture.verifiedPublication();
 await page.goto(`/analyses/${id}`);await page.getByRole('button',{name:'Draft',exact:true}).click();
 const publication=page.getByRole('dialog',{name:'Create ticket',exact:true});
 await publication.getByLabel('Publication connection',{exact:true}).selectOption('4');
 await publication.getByLabel('Project / repository',{exact:true}).selectOption('TEAM');
 await expect(publication.getByText('Publication preview',{exact:true})).toHaveCount(0);
 await expect(publication.getByText('See full content',{exact:true})).toHaveCount(0);
 await expect(publication.getByRole('heading',{name:'Need',exact:true})).toHaveCount(1);
 await publication.getByRole('button',{name:'Publish',exact:true}).click();
 expect(fixture.posts).toHaveLength(0);
 const confirmation=page.getByRole('alertdialog',{name:'Confirm publication',exact:true});
 await confirmation.getByRole('button',{name:'Confirm publication',exact:true}).click();
 await expect.poll(()=>fixture.posts.length).toBe(1);expect(fixture.deep).toBe(0);
});

test('required provider fields stay visible and optional assignation is searchable',async({page})=>{
 const fixture=await setup(page,'en',true);
 fixture.options({fields:[{id:'category',label:'Category',type:'text',required:true,options:[]}],assignees:[{id:'alice',name:'Alice Martin'},{id:'bob',name:'Bob Petit'}]});
 await page.goto(`/analyses/${id}`);await page.getByRole('button',{name:'Draft',exact:true}).click();
 const modal=page.getByRole('dialog',{name:'Create ticket',exact:true});
 await modal.getByRole('button',{name:'Edit',exact:true}).click();
 await modal.getByLabel('Description',{exact:true}).fill('My manually corrected scope.');
 await modal.getByLabel('Publication connection',{exact:true}).selectOption('4');
 await modal.getByLabel('Project / repository',{exact:true}).selectOption('TEAM');
 await expect(modal.getByLabel('Category *',{exact:true})).toBeVisible();
 await expect(modal.getByRole('button',{name:'Publish',exact:true})).toBeDisabled();
 await modal.getByLabel('Category *',{exact:true}).fill('Accounting');
 await modal.getByText('Additional options',{exact:true}).click();
 await modal.locator('summary').filter({hasText:'Assignees'}).click();
 await modal.getByLabel('Search Assignees',{exact:true}).fill('Bob');
 await expect(modal.getByRole('checkbox',{name:'Alice Martin',exact:true})).toHaveCount(0);
 await modal.getByRole('checkbox',{name:'Bob Petit',exact:true}).check();
 await expect(modal.locator('select[multiple]')).toHaveCount(0);
 await expect(modal.getByLabel('Description',{exact:true})).toHaveValue('My manually corrected scope.');
 await modal.getByRole('button',{name:'Save',exact:true}).click();
 await expect.poll(()=>fixture.destinationSaves.length).toBeGreaterThan(0);
 expect(fixture.destinationSaves.at(-1)).toMatchObject({body:'My manually corrected scope.',fields:{category:'Accounting'},assignees:['bob']});
 await modal.getByRole('button',{name:'Close',exact:true}).first().click();
 await page.getByRole('button',{name:'Draft',exact:true}).click();
 await modal.getByLabel('Publication connection',{exact:true}).selectOption('4');
 await modal.getByLabel('Project / repository',{exact:true}).selectOption('TEAM');
 await expect(modal.getByLabel('Category *',{exact:true})).toHaveValue('Accounting');
 expect(fixture.posts).toHaveLength(0);expect(fixture.generations).toBe(0);
});

test('a failed save on close keeps manual corrections without starting AI',async({page})=>{
 const fixture=await setup(page,'en',true);
 await page.goto(`/analyses/${id}`);await page.getByRole('button',{name:'Draft',exact:true}).click();
 const modal=page.getByRole('dialog',{name:'Create ticket',exact:true});
 await modal.getByLabel('Title',{exact:true}).fill('Unsaved correction');
 fixture.failSave();await modal.getByRole('button',{name:'Close',exact:true}).first().click();
 await expect(modal).toBeVisible();await expect(modal.getByText('Draft could not be saved.',{exact:true})).toBeVisible();
 await expect(modal.getByLabel('Title',{exact:true})).toHaveValue('Unsaved correction');
 await expect(modal.getByRole('button',{name:'Retry',exact:true})).toHaveCount(0);
 await modal.getByRole('button',{name:'Save',exact:true}).click();
 await modal.getByRole('button',{name:'Close',exact:true}).first().click();
 await page.getByRole('button',{name:'Draft',exact:true}).click();
 await expect(modal.getByLabel('Title',{exact:true})).toHaveValue('Unsaved correction');
 expect(fixture.generations).toBe(0);expect(fixture.posts).toHaveLength(0);
});

test('cancelling after document generation sends nothing and keeps the draft',async({page})=>{
 const fixture=await setup(page,'en',true);
 await page.goto(`/analyses/${id}`);await page.getByRole('button',{name:'Draft',exact:true}).click();
 const modal=page.getByRole('dialog',{name:'Create ticket',exact:true});
 await modal.getByLabel('Publication connection',{exact:true}).selectOption('4');
 await modal.getByLabel('Project / repository',{exact:true}).selectOption('TEAM');
 await modal.getByRole('button',{name:'Publish',exact:true}).click();
 await expect(page.getByRole('alertdialog')).toBeVisible();expect(fixture.documentRequests).toHaveLength(1);
 expect(fixture.posts).toHaveLength(0);
 await page.getByRole('alertdialog').getByRole('button',{name:'Cancel',exact:true}).click();
 await modal.getByRole('button',{name:'Close',exact:true}).first().click();
 await page.getByRole('button',{name:'Draft',exact:true}).click();
 await expect(modal.getByLabel('Title',{exact:true})).toHaveValue('Contribution rounding');
 expect(fixture.posts).toHaveLength(0);expect(fixture.deep).toBe(0);
});
