import { test, expect } from "./fixtures";
import { translate } from "../src/lib/i18n";

const id="41414141-4141-4141-8141-414141414141";
const at="2026-11-10T00:00:00Z";

for(const language of ["en","fr"] as const)for(const theme of ["light","dark"]){
  test(`conversation roles match connection tags and references stay in one disclosure in ${language} ${theme}`,async({page})=>{
    const t=(key:string)=>translate(key,language);
    const roles=["analyst","counter_analyst","verifier"];
    const paragraph=language==="fr"?"Sources : `backend/core/rules.py` (lignes 12–18), révision abc123. La configuration n’a pas été consultée.":"Sources: `backend/core/rules.py` (lines 12–18), revision abc123. The configuration was not inspected.";
    const response=[
      language==="fr"?"L’Analyste examine le besoin, le Contre-analyste le réexamine et le Validateur vérifie les conclusions.":"The Analyst examines the need, the Counter-analyst reviews it and the Verifier checks the conclusions.",
      "The calculation uses `rules.py`; this explanation remains visible.",
      paragraph,
      "Important conclusion after the references.",
      "Sources : les revenus déclarés restent à préciser.",
      "```text\nSources: `literal.py`\nAnalyst\n```",
    ].join("\n\n");
    const value={id,title:"Source presentation",need:"Explain the calculation.",workflow:"question",status:"DISCUSSING",conversation_state:"DISCUSSION",created_at:at,
      baseline:[],database:{},attachments:[],progress:[],questions:[],conversation:[],versions:[],latest_version:null,analysis_runs:[],
      discussion:{enabled:true,mode:"discussion",revision:1},messages:[{id:1,role:"user",kind:"need",content:"Explain the calculation.",created_at:at},
        {id:2,role:"assistant",kind:"discussion_reply",content:response,created_at:at}]};
    await page.addInitScript(theme=>localStorage.setItem("spechelper-theme",theme),theme);
    await page.route("**/api/**",route=>route.fulfill({json:[]}));
    await page.route("**/api/access/session",route=>route.fulfill({json:{mode:"local",authenticated:true}}));
    await page.route("**/api/settings",route=>route.fulfill({json:{name:"SpecHelper",language}}));
    await page.route("**/api/ai-connections",route=>route.fulfill({json:[{id:1,name:"ChatGPT",agent:"codex",roles,enabled:true,status:"CONNECTED",availability:"AVAILABLE"}]}));
    await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
    let reads=0;
    await page.route(`**/api/analyses/${id}/messages/2/sources`,route=>{
      reads++;return route.fulfill({json:{sources:[{id:"git",kind:"git",title:"backend/core/rules.py",repository:"team/app",commit:"a".repeat(40),line_start:12,line_end:18,excerpt:"verified = True"}]}});
    });
    await page.goto("/admin");
    const reference=page.locator("#ai-connection-1 .connection-role-tag");
    await expect(reference).toHaveCount(3);
    const styles=await reference.evaluateAll(nodes=>nodes.map(node=>{
      const style=getComputedStyle(node);return {color:style.color,background:style.backgroundColor,border:style.borderTopWidth,padding:style.padding,fontSize:style.fontSize};
    }));
    await page.goto(`/analyses/${id}`);
    const answer=page.locator('[data-message="message-2"]');
    const tags=answer.locator(".conversation-role-mention");
    await expect(tags).toHaveCount(3);
    for(let index=0;index<roles.length;index++){
      const actual=answer.locator(`.conversation-role-mention[data-role="${roles[index]}"]`);
      await expect(actual).toHaveText(t(["Analyst","Counter-analyst","Verifier"][index]));
      await expect.poll(()=>actual.evaluate(node=>{
        const style=getComputedStyle(node);return {color:style.color,background:style.backgroundColor,border:style.borderTopWidth,padding:style.padding,fontSize:style.fontSize};
      })).toEqual(styles[index]);
    }
    expect(new Set(styles.map(style=>style.color)).size).toBe(3);
    await expect(answer).toContainText("The calculation uses rules.py; this explanation remains visible.");
    await expect(answer).toContainText("Important conclusion after the references.");
    await expect(answer).toContainText("Sources : les revenus déclarés restent à préciser.");
    await expect(answer.locator("pre")).toContainText("Sources: `literal.py`");
    const sources=answer.locator(".source-details");
    await expect(sources).toHaveCount(1);
    await expect(sources).not.toHaveAttribute("open");
    await expect(answer.getByText("abc123",{exact:false})).toHaveCount(0);
    await expect(answer).toContainText(language==="fr"?"La configuration n’a pas été consultée.":"The configuration was not inspected.");
    expect(reads).toBe(0);
    await sources.locator(":scope > summary").click();
    await expect(sources.locator("[data-source-notes]")).toContainText("abc123");
    await expect(sources.locator("[data-source-notes]")).not.toContainText(language==="fr"?"La configuration n’a pas été consultée.":"The configuration was not inspected.");
    await sources.locator(".source-record > summary").click();
    await expect(sources.locator("pre")).toContainText("verified = True");
    expect(reads).toBe(1);
    await sources.locator(":scope > summary").click();
    await sources.locator(":scope > summary").click();
    expect(reads).toBe(1);
    await expect(sources.locator("[data-source-notes]")).toContainText("abc123");
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
}

for(const language of ["en","fr"] as const){
  test(`reference notes remain available when source loading fails in ${language}`,async({page})=>{
    const t=(key:string)=>translate(key,language);
    const value={id,title:"Unavailable source",need:"Explain the rule.",workflow:"question",status:"DISCUSSING",created_at:at,
      baseline:[],database:{},attachments:[],progress:[],questions:[],conversation:[],versions:[],analysis_runs:[],
      messages:[{id:2,role:"assistant",kind:"discussion_reply",content:"Sources: `unavailable.py`. No independent verification was completed.",created_at:at}]};
    await page.route("**/api/**",route=>route.fulfill({json:[]}));
    await page.route("**/api/access/session",route=>route.fulfill({json:{mode:"local",authenticated:true}}));
    await page.route("**/api/settings",route=>route.fulfill({json:{name:"SpecHelper",language}}));
    await page.route(`**/api/analyses/${id}`,route=>route.fulfill({json:value}));
    let reads=0;
    await page.route(`**/api/analyses/${id}/messages/2/sources`,route=>{
      reads++;return reads===1?route.fulfill({status:503,json:{detail:"Source service unavailable"}}):route.fulfill({json:{sources:[]}});
    });
    await page.goto(`/analyses/${id}`);
    const answer=page.locator('[data-message="message-2"]');
    await expect(answer).toContainText("No independent verification was completed.");
    const sources=answer.locator(".source-details");
    await sources.locator(":scope > summary").click();
    await expect(sources.getByRole("alert")).toContainText("Source service unavailable");
    await expect(sources.locator("[data-source-notes]")).toContainText("unavailable.py");
    await sources.getByRole("button",{name:t("Retry"),exact:true}).click();
    await expect(sources.getByRole("alert")).toHaveCount(0);
    await expect(sources.locator("[data-source-notes]")).toContainText("unavailable.py");
    await expect(sources.locator(".source-record")).toHaveCount(0);
    await expect(sources).not.toContainText(t("No source details were recorded for this answer."));
    expect(reads).toBe(2);
  });
}
