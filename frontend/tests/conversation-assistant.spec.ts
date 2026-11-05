import {test,expect} from "./fixtures";
import {translate} from "../src/lib/i18n";

const id="73737373-7373-4373-8373-737373737373";
const at="2026-11-01T10:00:00Z";
for(const language of ["en","fr"] as const){
 const t=(key:string)=>translate(key,language);
 for(const reason of ["quota_exhausted","analyst_role_removed","connection_unavailable"]){
 for(const target of reason === "quota_exhausted" ? ["codex","antigravity"] : ["codex"]){
  test(`${reason} transfer requires an explicit ${target} configuration choice in ${language}`,async({page})=>{
   let transfers=0;
   const selected={connection_id:1,name:"Original ChatGPT",agent:"codex",model:"original-model",reasoning_effort:"low",availability:reason === "quota_exhausted" ? "QUOTA_EXHAUSTED" : "AVAILABLE",continuation_reason:reason};
   const alternative={connection_id:2,name:target==="codex"?"Second ChatGPT":"Antigravity",agent:target,model:target==="codex"?"second-model":"gemini-model",reasoning_effort:target==="codex"?"ultra":"",configuration_token:"b".repeat(64)};
   let value:any={id,title:"Benefit behavior",need:"Explain benefits",original_need:"Explain benefits",workflow:"question",intent_mode:"auto",environment_name:"Staging",environment_id:1,status:"QUEUED",result_state:"waiting_ai",created_at:at,analysis_protocol:"2.4",baseline:[],database:{},attachments:[],progress:[],error:"",understanding:"",questions:[],conversation:[],latest_version:null,versions:[],decision_revision:0,decisions:[],decision_history:[],validated_version:null,conclusions_stale:false,messages:[{id:1,role:"user",kind:"need",content:"Explain benefits",created_at:at}],analysis_runs:[],discussion:{enabled:true,mode:"discussion",revision:1,has_new_messages:true,connection_id:1,assistant:selected,assistant_history:[{...selected,current:true,used:false}],job:{id:1,status:"QUEUED",created_at:at,error:"",waiting_reason:"Waiting for the selected AI connection."}}};
   if(reason !== "quota_exhausted")value={...value,status:"DISCUSSING",result_state:"discussion",discussion:{...value.discussion,job:{...value.discussion.job,status:"DONE",waiting_reason:""}}};
   await page.route("**/api/**",r=>r.fulfill({json:[]}));
   await page.route("**/api/access/session",r=>r.fulfill({json:{authenticated:true,mode:"local"}}));
   await page.route("**/api/settings",r=>r.fulfill({json:{name:"SpecHelper",language}}));
   await page.route(`**/api/analyses/${id}`,r=>r.fulfill({json:value}));
   await page.route(`**/api/analyses/${id}/discussion/continuation-options`,r=>r.fulfill({json:{revision:1,can_continue:true,options:[alternative]}}));
   await page.route(`**/api/analyses/${id}/discussion`,r=>r.fulfill({status:409,json:{detail:"Choose an AI connection allowed to act as analyst."}}));
   await page.route(`**/api/analyses/${id}/discussion/continue-with`,r=>{
    transfers++;
    expect(r.request().postDataJSON()).toEqual({expected_revision:1,connection_id:2,configuration_token:alternative.configuration_token});
    value={...value,discussion:{...value.discussion,revision:2,connection_id:2,assistant:{...alternative,availability:"AVAILABLE"},assistant_history:[{...selected,current:false,used:false},{...alternative,current:true,used:false}]}};
    return r.fulfill({json:value});
   });
   await page.goto(`/analyses/${id}`);
   const control=page.getByLabel(t("Conversation assistant"),{exact:true});
   await expect(control).toContainText("Original ChatGPT");
   const tag=control.locator(".connection-model-tag");
   await expect(tag).toHaveText("original-model low");
   expect(await tag.evaluate(el=>getComputedStyle(el).getPropertyValue("--tag-ink").trim())).not.toBe("");
   if(reason === "quota_exhausted")await expect(control.getByText(t("Quota limit reported"),{exact:true})).toBeVisible();
   else {
    await expect(control).toContainText(t(reason === "analyst_role_removed" ? "The selected assistant no longer has the Analyst role. Choose another assistant to continue." : "The selected AI connection is no longer available. Choose another assistant to continue."));
    await expect(control.getByText(t("Quota limit reported"),{exact:true})).toHaveCount(0);
    await page.getByLabel(t("Your message"),{exact:true}).fill("Continue my question.");
    await page.getByRole("button",{name:t("Send message"),exact:true}).click();
    await expect(page.getByRole("alert").filter({hasText:t("Choose an AI connection allowed to act as analyst.")})).toBeVisible();
   }
   await control.getByRole("button",{name:t("Continue the analysis with…"),exact:true}).click();
   const choice=control.getByLabel(t("Available assistant"),{exact:true});
   await expect(choice).toHaveValue("");
   await expect(control.getByRole("button",{name:t("Continue"),exact:true})).toBeDisabled();
   await choice.selectOption("2");
   await expect(choice.locator("option:checked")).toContainText(alternative.model);
   if(target==="codex")await expect(choice.locator("option:checked")).toContainText("ultra");
   expect(transfers).toBe(0);
   await control.getByRole("button",{name:t("Cancel"),exact:true}).click();
   expect(transfers).toBe(0);
   await control.getByRole("button",{name:t("Continue the analysis with…"),exact:true}).click();
   await control.getByLabel(t("Available assistant"),{exact:true}).selectOption("2");
   await control.getByRole("button",{name:t("Continue"),exact:true}).click();
   await expect(control).toContainText(alternative.name);
   if(reason !== "quota_exhausted"){
    await expect(page.getByRole("alert").filter({hasText:t("Choose an AI connection allowed to act as analyst.")})).toHaveCount(0);
    await expect(page.getByLabel(t("Your message"),{exact:true})).toHaveValue("Continue my question.");
   }
   await expect(control.locator(".connection-model-tag").first()).toContainText(alternative.model);
   const history=page.getByLabel(t("AI history"),{exact:true});
   await expect(history).toContainText("Original ChatGPT");
   await expect(history).toContainText("original-model low");
   await expect(control.getByText(t("Current assistant"),{exact:true})).toBeVisible();
   await page.reload();
   await expect(page.getByLabel(t("AI history"),{exact:true})).toContainText("original-model low");
   await expect(control.getByRole("button",{name:t("Continue the analysis with…"),exact:true})).toHaveCount(0);
   expect(transfers).toBe(1);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
 }
}
}
