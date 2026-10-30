"use client";

import { useI18n } from "@/lib/i18n";
import { roleLabels } from "@/lib/orchestration";

// Tag explicit role names only; never infer an author from the message content.
const names:Record<string,string>={analyst:"analyst",analyste:"analyst","counter-analyst":"counter_analyst","contre-analyste":"counter_analyst",verifier:"verifier",validateur:"verifier",vérificateur:"verifier",verificateur:"verifier"};
const mentions=/(?<![\p{L}\p{N}_-])(counter[- ]analyst|contre[- ]analyste|analyste|analyst|validateur|vérificateur|verificateur|verifier)(?![\p{L}\p{N}_-])/giu;

export function RoleMentions({children}:{children:string}) {
  const {t}=useI18n();
  return children.split(mentions).map((text,index)=>{
    const role=names[text.toLowerCase().replace(/ /g,"-")];
    return role ? <span key={index} className="badge conversation-role-mention" data-role={role}>{t(roleLabels[role])}</span> : text;
  });
}
