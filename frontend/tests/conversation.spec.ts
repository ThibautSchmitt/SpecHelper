import { test, expect } from "./fixtures";
import { translate } from "../src/lib/i18n";
import { readFile } from "node:fs/promises";

const id = "29292929-2929-4292-8292-292929292929";
const at = "2026-10-28T10:00:00Z";
const later = "2026-10-28T10:05:00Z";
function dossier() {
  const version = { id:"version",number:1,format_version:"2.9",status:"PARTIAL",language:"en",created_at:"2026-10-28T10:07:00Z",run_number:1,
    explanation:{title:"Benefit dates",summary:"Imported dates need a separate check."},ticket:{},markdown:"Full report",answer_markdown:"Full report",goal_markdown:"",artifacts:{},
    evidence:{claims:[],blocking:true,limitations:["Database records were not inspected."],database:{status:"not_configured",limitations:[],checks:[],scope:""}},decisions_snapshot:[] };
  return {id,title:"Benefit dates",need:"Explain inconsistent benefit dates.",original_need:"Explain inconsistent benefit dates.",workflow:"question",intent_mode:"auto",environment_name:"Production",environment_id:1,
    status:"NEEDS_CLARIFICATION",result_state:"clarification",created_at:at,analysis_protocol:"2.4",baseline:[],database:{},attachments:[],progress:[],error:"",understanding:"Check the affected benefit screen.",
    questions:[{id:"screen",question:"Which screen is affected?"}],conversation:[],latest_version:null as typeof version|null,versions:[] as {number:number;created_at:string;status:string}[],decision_revision:0,decisions:[],decision_history:[],validated_version:null,conclusions_stale:false,
    messages:[{id:1,role:"user",kind:"need",content:"Explain inconsistent benefit dates.",created_at:at,version_number:null},
      {id:2,role:"assistant",kind:"clarification",content:"Which screen is affected?",created_at:later,version_number:null,data:{public_role:"counter_analyst",run_number:1}}] as Record<string,unknown>[],
    analysis_runs:[{number:1,status:"NEEDS_CLARIFICATION",steps:[{public_role:"analyst",status:"DONE",provider:"codex"},{public_role:"counter_analyst",status:"DONE",provider:"antigravity"}],role_reviews:[{checkpoint:"analyst",public_role:"analyst",summary:"The screen checks dates.",findings:[],issues:[],agreements:[],limits:[]}]}],
    _version:version};
}

import type { Page } from "@playwright/test";

function execution(status:string,current_role:string,states:string[],causes:string[]=[]) {
  return {status,current_role,checkpoint:current_role,waiting_reason:causes.length?"No available AI connection is allowed to perform this role.":"",waiting_causes:causes,all_stages_done:states.every(state=>state==="done"),stages:["analyst","counter_analyst","verifier"].map((role,index)=>({role,status:states[index]}))};
}
async function setup(page:Page,language:"en"|"fr",read:()=>unknown,name="Acme",theme="dark") {
  await page.addInitScript(theme=>localStorage.setItem("spechelper-theme",theme),theme);
  await page.route("**/api/**",route=>route.fulfill({json:[]}));
  await page.route("**/api/access/session",route=>route.fulfill({json:{authenticated:true,mode:"local"}}));
  await page.route("**/api/settings",route=>route.fulfill({json:{name,language,primary_color:"#168e95"}}));
  await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:read()}));
}

for(const language of ["en","fr"] as const) {
 const t=(key:string)=>translate(key,language);
 test(`explicit role mentions use tags without adding speakers in ${language}`,async({page})=>{
  const source=dossier();
  const question=language === 'fr' ? 'Le Contre-analyste a une question : cet écran est-il concerné ?' : 'The Counter-analyst has a question: is this screen affected?';
  const summary=language === 'fr' ? 'L’Analyste pense que la période est incorrecte. Le Contre-analyste demande une précision. Le Vérificateur a trouvé une limite.' : 'The Analyst suspects an invalid period. The Counter-analyst needs a clarification. The Verifier found a limit.';
  let current:any={...source,questions:[{id:'screen',question}],messages:[source.messages[0],{...source.messages[1],content:question}]};
  await setup(page,language,()=>current);
  await page.goto(`/analyses/${id}`);
  await expect(page.locator('legend .conversation-role-mention')).toHaveAttribute('data-role','counter_analyst');
  await expect(page.locator('.conversation-pending-author strong')).toHaveCount(0);
  current={...current,status:'PARTIAL',questions:[],latest_version:{...source._version,explanation:{title:'Conclusion',summary:summary+' Code identifier: `Analyst`.',business_explanation:'Code identifier: `Analyst`. General analysts are not role mentions.'}},versions:[{number:1,status:'PARTIAL',created_at:source._version.created_at}]};
  const final=page.locator('[data-message="result-1"]');
  await expect(final.locator('.conversation-role-mention')).toHaveCount(3);
  for(const role of ['analyst','counter_analyst','verifier'])await expect(final.locator(`.conversation-role-mention[data-role="${role}"]`)).toBeVisible();
  await expect(final.locator('.conversation-role-mention[data-role="verifier"]')).toHaveText(t('Verifier'));
  if(language === 'fr')expect(t('Verifier')).toBe('Validateur');
  await expect(final.locator('code')).toHaveText('Analyst');
  await expect(page.locator('.conversation-user .conversation-role-mention')).toHaveCount(0);
  await expect(final.locator('header strong')).toHaveCount(0);
 });
 test(`individual reports are optional downloads outside the ticket in ${language}`,async({page})=>{
  const source=dossier();
  const roles=[['analyst','Analyst'],['counter_analyst','Counter-analyst'],['verifier','Verifier']] as const;
  const current={...source,status:"PARTIAL",questions:[],latest_version:source._version,versions:[{number:1,status:"PARTIAL",created_at:source._version.created_at}],analysis_runs:[{...source.analysis_runs[0],role_reviews:roles.map(([role])=>({checkpoint:role === 'counter_analyst' ? 'comparison' : role,public_role:role,summary:`Recorded ${role} conclusion`,findings:[{statement:`Evidence from ${role}`,sources:[{path:'benefits/dates.ts',line:42}]}],agreements:[],issues:[],limits:['Data access was unavailable.']}))}]};
  await setup(page,language,()=>current);
  const mutations:string[]=[];
  page.on('request',request=>{if(request.url().includes('/api/')&&!['GET','HEAD'].includes(request.method()))mutations.push(request.url());});
  await page.goto(`/analyses/${id}`);
  await expect(page.locator('.investigation-review')).toHaveCount(0);
  const downloads=page.getByRole('region',{name:t('Individual AI reports'),exact:true});
  await expect(downloads).not.toBeVisible();
  await page.getByRole('button',{name:t('Analysis report'),exact:true}).click();
  for(const [role,label] of roles){
   const event=page.waitForEvent('download');
   await downloads.getByRole('button',{name:`${t(label)} · .md`,exact:true}).click();
   const download=await event;
   expect(download.suggestedFilename()).toBe(`analysis-${id}-v1-${role}.md`);
   const content=await readFile((await download.path())!,'utf8');
   expect(content).toContain(`Recorded ${role} conclusion`);
   expect(content).toContain('benefits/dates.ts');
   expect(content).toContain(t('Partial result'));
  }
  expect(mutations).toEqual([]);
 });
 test(`delete analysis requires confirmation and preserves the page on failure in ${language}`,async({page})=>{
  await setup(page,language,()=>dossier());
  let deletions=0;
  await page.route(`**/api/analyses/${id}`,async route=>{
   if(route.request().method() !== "DELETE")return route.fulfill({json:dossier()});
   expect(route.request().postDataJSON()).toEqual({confirmed:true});
   deletions++;
   return deletions === 1 ? route.fulfill({status:409,json:{detail:"Cancel the analysis and wait for its agents to stop before deleting it."}}) : route.fulfill({json:{status:"DELETED"}});
  });
  await page.goto(`/analyses/${id}`);
  const trigger=page.getByRole("button",{name:t("Delete analysis"),exact:true});
  const dialog=page.getByRole("dialog",{name:t("Delete analysis"),exact:true});
  await trigger.click();await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(t("It will be removed from Analyses, Home and Activity. Published tickets and their audit records are kept. This action cannot be undone in the application."));
  await dialog.getByRole("button",{name:t("Cancel"),exact:true}).click();
  await expect(dialog).not.toBeVisible();expect(deletions).toBe(0);
  await expect(trigger).toBeFocused();
  await trigger.click();await page.keyboard.press("Escape");await expect(dialog).not.toBeVisible();
  await trigger.click();await dialog.getByRole("button",{name:t("Confirm deletion"),exact:true}).click();
  await expect(dialog.getByRole("alert")).toHaveText(t("Cancel the analysis and wait for its agents to stop before deleting it."));
  await expect(page).toHaveURL(new RegExp(`/analyses/${id}$`));
  await dialog.getByRole("button",{name:t("Confirm deletion"),exact:true}).click();
  await expect(page).toHaveURL(/\/analyses$/);expect(deletions).toBe(2);
 });
 test(`delete analysis is unavailable while agents work in ${language}`,async({page})=>{
  await setup(page,language,()=>({...dossier(),status:"ANALYZING",questions:[]}));
  await page.goto(`/analyses/${id}`);
  await expect(page.getByRole("button",{name:t("Delete analysis"),exact:true})).toBeDisabled();
 });
 for(const theme of ["light","dark"]) {
  test(`one named assistant and one live progress per cycle in ${language} ${theme}`,async({page},info)=>{
   const source=dossier();
   const acceptedVersion={...source._version,explanation:{...source._version.explanation,business_explanation:"The accepted comparison found a **boundary case**. An additional data check is required."}};
   let current:any={...source,analysis_runs:[{...source.analysis_runs[0],started_at:"2026-10-28T10:00:01Z",execution:execution("NEEDS_CLARIFICATION","counter_analyst",["done","clarification","waiting"])}]};
   const writes:string[]=[];
   await setup(page,language,()=>current,"Acme",theme);
   await page.route(`**/api/questions/${id}/answers`,route=>{
    writes.push("answer");
    expect(route.request().postDataJSON()).toMatchObject({answers:{screen:"In the benefit dossier."},expected_decision_revision:0});
    current={...current,status:"QUEUED",result_state:"waiting_ai",questions:[],messages:[...current.messages,{id:3,role:"user",kind:"answer",content:"In the benefit dossier.",data:{answers:{screen:"In the benefit dossier."}},created_at:"2026-10-28T10:06:00Z"}],analysis_runs:[{...current.analysis_runs[0],status:"QUEUED",execution:execution("QUEUED","counter_analyst",["done","blocked","waiting"],["quota"])}]};
    return route.fulfill({json:current});
   });
   await page.route(`**/api/analyses/${id}/discussion`,route=>{
    writes.push("followup");
    expect(route.request().postDataJSON()).toEqual({message:"Check the exception.",expected_revision:0,restart_session:false});
    current={...current,status:"QUEUED",discussion:{enabled:true,mode:"discussion",revision:1,has_new_messages:true,connection_id:1,job:{id:2,status:"QUEUED",created_at:"2026-10-28T10:08:01Z",waiting_reason:"",error:""}},messages:[...current.messages,{id:4,role:"user",kind:"discussion",content:"Check the exception.",created_at:"2026-10-28T10:08:00Z"}]};
    return route.fulfill({json:current});
   });
   await page.goto(`/analyses/${id}`);
   const thread=page.getByRole("region",{name:t("Business conversation"),exact:true});
   await expect(page.getByRole("button",{name:t("Show roles"),exact:true})).toHaveCount(0);
   await expect(page.locator(".conversation-pending-author strong")).toHaveCount(0);
   await expect(page.locator(".conversation-pending-author [data-role]")).toHaveCount(0);
   await expect(page.locator(".conversation-brand-avatar")).toHaveCount(2);
   const icons=await page.locator('.conversation-brand-avatar').evaluateAll(nodes=>nodes.map(node=>({border:getComputedStyle(node).borderTopWidth,background:getComputedStyle(node).backgroundColor,shadow:getComputedStyle(node).boxShadow})));
   expect(icons.every(icon=>icon.border === "0px" && icon.background === "rgba(0, 0, 0, 0)" && icon.shadow === "none")).toBe(true);
   await expect(thread.locator("legend").filter({hasText:/^Which screen is affected\?$/})).toHaveCount(1);
   const progress=thread.locator('[data-cycle="1"]');
   await expect(thread.locator(".investigation-progress")).toHaveCount(1);
   await expect(thread.locator('.conversation-user .conversation-avatar')).toHaveCount(0);
   await expect(thread.locator('header strong')).toHaveCount(0);
   await page.screenshot({path:`../.local/single-assistant-compact-${language}-${theme}-${info.project.name}.png`,fullPage:true});
   await progress.locator(":scope > summary").click();
   const handle=await progress.elementHandle();
   await expect(progress.locator('[data-stage-status="done"]')).toHaveCount(1);
   await expect(progress.locator('[data-stage="counter_analyst"]')).toContainText(t("Clarification requested"));
   const rows=await progress.locator('.investigation-stages > li').evaluateAll(nodes=>nodes.map(node=>({top:node.getBoundingClientRect().top,border:getComputedStyle(node).borderTopWidth})));
   expect(rows).toHaveLength(3);
   expect(rows[1].top).toBeGreaterThan(rows[0].top);
   expect(rows[2].top).toBeGreaterThan(rows[1].top);
   expect(rows.every(row=>row.border === "0px")).toBe(true);
   await expect(progress.locator('.investigation-subtitle')).toHaveText(t("A business clarification is needed before continuing."));
   await page.screenshot({path:`../.local/progress-clarification-${language}-${theme}-${info.project.name}.png`,fullPage:true});
   await expect(progress.getByText(t("A completed stage records execution, not a guarantee that its conclusions are correct."),{exact:true})).not.toBeVisible();
   await expect(progress.locator('.investigation-review')).toHaveCount(0);
   await expect(progress.getByText("The screen checks dates.",{exact:true})).toHaveCount(0);
   expect(writes).toEqual([]);
   await page.getByLabel("Which screen is affected?",{exact:true}).fill("In the benefit dossier.");
   await page.getByRole("button",{name:t("Answer and continue"),exact:true}).click();
   await expect(progress).toHaveAttribute("open","");
   const order=await thread.locator('.conversation-messages > li').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('data-message')));
   expect(order.indexOf('progress-1')).toBeGreaterThan(order.indexOf('message-3'));
   await expect(progress.getByText(t("Quota exhausted"),{exact:true})).toBeVisible();
   await expect(progress.locator('.investigation-subtitle')).toHaveText(t("The counter-analysis will resume when an assistant is available."));
   await page.screenshot({path:`../.local/progress-waiting-${language}-${theme}-${info.project.name}.png`,fullPage:true});
   await expect(page.getByLabel(t("Your message"),{exact:true})).toBeDisabled();
   expect(await handle!.evaluate(node=>node.isConnected)).toBe(true);
   await expect(thread.locator(".investigation-progress")).toHaveCount(1);
   current={...current,status:"ANALYZING",analysis_runs:[{...current.analysis_runs[0],status:"ANALYZING",execution:execution("ANALYZING","counter_analyst",["done","running","waiting"])}]};
   await expect(progress.locator(":scope > summary")).toContainText(t("Counter-analysis in progress…"),{timeout:10000});
   await expect(progress.locator('.investigation-heading > span').first()).toHaveText(t("Analysis in progress"));
   await page.screenshot({path:`../.local/progress-list-${language}-${theme}-${info.project.name}.png`,fullPage:true});
   current={...current,status:"PARTIAL",latest_version:acceptedVersion,versions:[{number:1,status:"PARTIAL",created_at:source._version.created_at}],analysis_runs:[{...current.analysis_runs[0],status:"PARTIAL",execution:execution("PARTIAL","verifier",["done","done","done"])}]};
   await expect(progress.locator(":scope > summary")).toContainText(t("Investigation finished"),{timeout:10000});
   await expect(progress.locator('[data-stage-status="done"]')).toHaveCount(3);
   const final=thread.locator('[data-message="result-1"]');
   await expect(final).toContainText("Imported dates need a separate check.");
   await expect(final).not.toContainText("The accepted comparison found a boundary case.");
   await expect(final.locator('strong').filter({hasText:'boundary case'})).toHaveCount(0);
   await expect(thread.locator('.investigation-review')).toHaveCount(0);
   await expect(thread.getByText("The screen checks dates.",{exact:true})).toHaveCount(0);
   await expect(final).not.toContainText("Database records were not inspected.");
   await expect(page.locator("#analysis-report .mt-5.space-y-6")).toHaveCount(0);
   await expect(final).toContainText(t("Some conclusions remain unverified. See the analysis report for the limits and evidence."));
   await page.screenshot({path:`../.local/single-assistant-${language}-${theme}-${info.project.name}.png`,fullPage:true});
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   const input=page.getByLabel(t("Your message"),{exact:true});
   await input.fill("Check the exception.");
   await input.press("Shift+Enter");
   await expect(input).toHaveValue("Check the exception.\n");
   await input.dispatchEvent("keydown",{key:"Enter",isComposing:true});
   expect(writes).toHaveLength(1);
   await input.press("Backspace");await input.press("Enter");
   await expect(thread.locator('[data-message="discussion-progress-1"]')).toBeVisible();
   await expect(thread.locator(".investigation-progress")).toHaveCount(1);
   await expect(thread.locator('[data-cycle="1"] > summary')).toContainText(t("Investigation finished"));
   expect(writes).toEqual(["answer","followup"]);
  });
 }
 test(`historical attribution does not add speaker labels or clarification details in ${language}`,async({page})=>{
  const current:any=dossier();
  current.messages[1].attribution={run_number:1,public_role:"analyst",provider:"codex",source:"recorded_history"};
  await setup(page,language,()=>current);
  await page.goto(`/analyses/${id}`);
  await expect(page.locator(".conversation-pending-author strong")).toHaveCount(0);
  await expect(page.locator(".conversation-pending-author")).not.toContainText("ChatGPT");
  await expect(page.locator(".conversation-question-details")).toHaveCount(0);
 });
 test(`unknown historical progress does not become complete in ${language}`,async({page})=>{
  const source=dossier();const current:any={...source,status:"PARTIAL",messages:[],questions:[],conversation:[{questions:[{id:"screen",question:"Which screen is affected?"}],answers:{screen:"In the benefit dossier."}}],latest_version:source._version,versions:[{number:1,status:"PARTIAL",created_at:later}],analysis_runs:[{number:1,status:"PARTIAL",steps:[],execution:execution("PARTIAL","verifier",["done","done","unknown"])}]};
  await setup(page,language,()=>current,"SpecHelper");await page.goto(`/analyses/${id}`);
  const thread=page.getByRole("region",{name:t("Business conversation"),exact:true});
  await expect(thread.getByText("In the benefit dossier.",{exact:true})).toBeVisible();
  const progress=thread.locator('[data-cycle="1"]');
  await expect(progress.locator(":scope > summary")).toContainText(t("Investigation finished · verification incomplete"));
  await progress.locator(":scope > summary").click();
  await expect(progress.locator('[data-stage="verifier"]')).toContainText(t("Stage completion not recorded"));
 });
 test(`recorded quota, busy and missing-connection causes stay separate in ${language}`,async({page})=>{
  let current:any={...dossier(),status:"QUEUED",questions:[],analysis_runs:[{number:1,status:"QUEUED",steps:[],execution:execution("QUEUED","analyst",["blocked","waiting","waiting"],["quota"])}]};
  await setup(page,language,()=>current);await page.goto(`/analyses/${id}`);
  const progress=page.locator('[data-cycle="1"]');await progress.locator(":scope > summary").click();
  for(const [cause,label] of [["quota","Quota exhausted"],["busy","Assistant busy"],["connection_missing","No authenticated connection"],["model_unavailable","Model unavailable"]]){
   current={...current,analysis_runs:[{...current.analysis_runs[0],execution:execution("QUEUED","analyst",["blocked","waiting","waiting"],[cause])}]};
   await expect(progress.locator('[data-stage="analyst"]')).toContainText(t(label),{timeout:10000});
   await expect(progress.locator('[data-stage="analyst"]').getByText(t(label),{exact:true})).toHaveCount(1);
   await expect(progress.locator('[data-stage="analyst"]').getByText(t('AI unavailable'),{exact:true})).toHaveCount(0);
   await expect(page.locator(".investigation-progress")).toHaveCount(1);
  }
 });
 test(`final drafting remains separate from completed roles and waiting tags match in ${language}`,async({page})=>{
  let current:any={...dossier(),status:"QUEUED",result_state:"waiting_ai",questions:[],messages:[dossier().messages[0]],analysis_runs:[{number:1,status:"QUEUED",steps:[],execution:{...execution("QUEUED","verifier",["done","done","done"],["unavailable"]),checkpoint:"writer"}}]};
  await setup(page,language,()=>current);
  await page.route('**/api/queue',route=>route.fulfill({json:[{id:65,kind:'analysis',request_id:id,title:'Benefit dates',status:'QUEUED',queue_state:'WAITING_AI',analysis_state:'waiting_ai',request_status:'QUEUED',href:`/analyses/${id}`,created_at:at}]}));
  await page.goto(`/analyses/${id}`);
  const progress=page.locator('.investigation-progress');
  await expect(progress.locator(':scope > summary')).toContainText(t('Final response awaiting an assistant'));
  await progress.locator(':scope > summary').click();
  await expect(progress.locator('[data-stage-status="done"]')).toHaveCount(3);
  await expect(progress.locator('[data-stage="verifier"]')).not.toContainText(t('Unavailable'));
  await expect(progress.getByText(t('Unavailable'),{exact:true})).toHaveCount(0);
  const style=await page.locator('.conversation-state').evaluate(node=>{
   const s=getComputedStyle(node);return [s.color,s.backgroundColor,s.borderRadius,s.padding,s.fontSize,s.fontWeight];
  });
  await page.getByRole('button',{name:t('Activity'),exact:true}).click();
  const activityBadge=page.locator('[data-job="65"] .badge:visible');
  await expect(activityBadge).toHaveText(t('Waiting for an AI resource'));
  expect(await activityBadge.evaluate(node=>{
   const s=getComputedStyle(node);return [s.color,s.backgroundColor,s.borderRadius,s.padding,s.fontSize,s.fontWeight];
  })).toEqual(style);
  current={...current,status:'ANALYZING',analysis_runs:[{...current.analysis_runs[0],status:'ANALYZING',execution:{...current.analysis_runs[0].execution,status:'ANALYZING',waiting_reason:'',waiting_causes:[]}}]};
  await expect(progress.locator(':scope > summary')).toContainText(t('Preparing final response…'));
  await expect(progress.locator('[data-stage-status="done"]')).toHaveCount(3);
  await page.route('**/api/analyses?**',route=>route.fulfill({json:{items:[{...current,status:'QUEUED',result_state:'waiting_ai',href:`/analyses/${id}`,latest_activity_at:at,latest_version_number:null,intent_resolved:true}],total:1,page:1,pages:1,has_previous:false,has_next:false}}));
  await page.goto('/analyses');
  const badge=page.locator('.analysis-state-pill');
  await expect(badge).toHaveText(t('Waiting for an AI resource'));
  expect(await badge.evaluate(node=>{
   const s=getComputedStyle(node);return [s.color,s.backgroundColor,s.borderRadius,s.padding,s.fontSize,s.fontWeight];
  })).toEqual(style);
 });
}
