import { test, expect } from "./fixtures";

test("model catalog preserves unknown access and restricts connection selection to listed options", async ({ page }) => {
  const connections = [{id:11,name:"Team assistant",agent:"codex",model:"",enabled:true,status:"CONNECTED",availability:"AVAILABLE",account:"fixture",roles:["analyst","counter_analyst","verifier"]}];
  let items = [{id:1,agent:"codex",identifier:"documented-model",name:"Documented model",family:"openai",source:"administered",status:"UNKNOWN",checked_at:null,enabled:true}];
  let refreshed = 0;
  let body: Record<string, unknown> | null = null;
  await page.route("**/api/connections", r => r.fulfill({json:{github:{status:"DISCONNECTED",account:""},ais:connections,databases:[]}}));
  await page.route("**/api/environments", r => r.fulfill({json:[]}));
  await page.route("**/api/queue", r => r.fulfill({json:[]}));
  await page.route("**/api/ai-connections", r => {
    if(r.request().method()==="POST") body=r.request().postDataJSON();
    return r.fulfill({json:connections});
  });
  await page.route("**/api/ai-models?*", r => r.fulfill({json:{items,discovery:{state:refreshed?"supported":"unknown",reason:refreshed?"catalog_not_entitlement":"not_refreshed"}}}));

  await page.route("**/api/ai-connections/11/models/refresh", r => {refreshed++; items=items.map(item=>({...item,status:"SUPPORTED"})); return r.fulfill({json:{items,discovery:{state:"supported",reason:"catalog_not_entitlement"}}});});
  await page.route("**/api/ai-connections/11", r => { body=r.request().postDataJSON(); return r.fulfill({json:{...connections[0],...body}}); });
  await page.goto("/admin");
  await page.getByRole("button", {name:"AI & Agents",exact:true}).click();
  await expect(page.getByRole("button", {name:"Models",exact:true})).toHaveCount(0);
  await page.getByRole("region", { name: "Team assistant", exact: true }).getByRole("button", {name:"Edit",exact:true}).click();
  const choice=page.getByLabel("Model",{exact:true});
  await expect(choice.locator("option")).toHaveCount(1);
  await page.getByRole("button",{name:"Refresh models",exact:true}).click();
  await expect.poll(()=>refreshed).toBe(1);
  await expect(choice.locator("option")).toHaveCount(2);
  await choice.selectOption("documented-model");
  await expect(page.getByLabel("Reasoning", {exact:true}).locator("option")).toHaveText(["Default"]);
  await page.getByRole("button",{name:"Save",exact:true}).click();
  await expect.poll(()=>body).toMatchObject({model:"documented-model",name:"Team assistant", reasoning_effort:""});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
