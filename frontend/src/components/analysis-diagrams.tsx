"use client";

import { useEffect, useId, useState } from "react";
import { Copy, Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import type { ReviewedDiagram } from "@/lib/analysis-evidence";

function Diagram({ diagram }: { diagram: ReviewedDiagram }) {
  const { t } = useI18n();
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "_");
  const [open, setOpen] = useState(false);
  const [image, setImage] = useState("");
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState(100);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  useEffect(() => {
    if (!open) return;
    let current = true;
    setImage(""); setFailed(false);
    import("mermaid").then(async ({ default: mermaid }) => {
      mermaid.initialize({ startOnLoad: false, securityLevel: "strict", htmlLabels: false,
        suppressErrorRendering: true, maxEdges: 40, maxTextSize: 30000,
        fontFamily: "system-ui, sans-serif" });
      const { svg } = await mermaid.render(`diagram_${id}`, diagram.mermaid);
      if (current) setImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`);
    }).catch(() => { if (current) setFailed(true); });
    return () => { current = false; };
  }, [open, diagram.mermaid, id]);

  return <details className="min-w-0 rounded-xl border bg-card p-5" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer font-medium">{diagram.proposal.title}</summary>
    <div className="mt-4 min-w-0 space-y-4">
      <p className="text-sm">{diagram.proposal.purpose}</p>
      <p id={`diagram-description-${id}`} className="whitespace-pre-wrap text-sm muted">{diagram.proposal.alternative_text}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" aria-label={t("Zoom out")} disabled={zoom <= 50} onClick={() => setZoom(value => value - 25)}><Minus size={16} aria-hidden="true" /></Button>
        <span className="text-sm tabular-nums" aria-live="polite">{zoom}%</span>
        <Button type="button" variant="outline" aria-label={t("Zoom in")} disabled={zoom >= 300} onClick={() => setZoom(value => value + 25)}><Plus size={16} aria-hidden="true" /></Button>
        <Button type="button" variant="outline" onClick={async () => {
          try { await navigator.clipboard.writeText(diagram.mermaid); setCopied(true); setCopyError(false); }
          catch { setCopyError(true); }
        }}><Copy size={16} aria-hidden="true" />{t(copied ? "Copied!" : "Copy Mermaid")}</Button>
      </div>
      {copyError && <p role="status" className="text-sm">{t("Copying is unavailable. Select the Mermaid source below.")}</p>}
      {failed ? <p role="status" className="rounded-lg border border-amber-500/50 p-3 text-sm">{t("The diagram could not be rendered. Its explanation and Mermaid source remain available.")}</p> : image ? <div className="max-h-[70vh] overflow-auto rounded-lg border bg-white p-3" tabIndex={0} role="region" aria-label={diagram.proposal.title}>
        {/* An image document cannot execute SVG scripts or follow embedded links. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={image} alt={diagram.proposal.alternative_text} aria-describedby={`diagram-description-${id}`} style={{ width: `${zoom}%`, maxWidth: "none", height: "auto" }} />
      </div> : open && <p role="status" className="text-sm muted">{t("Rendering diagram…")}</p>}
      <details open={failed || undefined} className="rounded-lg border p-3">
        <summary className="cursor-pointer text-sm font-medium">{t("Mermaid source")}</summary>
        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words text-xs" tabIndex={0}>{diagram.mermaid}</pre>
      </details>
      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer text-sm font-medium">{t("Relationship checks")}</summary>
        <ul className="mt-3 space-y-3 text-sm">{diagram.proposal.edges.map(edge => <li key={edge.id} className="space-y-1">
          <p className="font-medium">{edge.label} · {t(edge.meaning === "existing" ? "Existing" : edge.meaning === "hypothesis" ? "Hypothesis" : "Proposed change")}</p>
          <p>{diagram.reviews.find(review => review.edge_id === edge.id)?.notes}</p>
          {!!edge.claim_ids.length && <p className="text-xs muted">{edge.claim_ids.join(" · ")}</p>}
        </li>)}</ul>
      </details>
    </div>
  </details>;
}

export function AnalysisDiagrams({ diagrams }: { diagrams?: ReviewedDiagram[] }) {
  const { t } = useI18n();
  if (!diagrams?.length) return null;
  return <section className="min-w-0 space-y-3" aria-label={t("Explanatory diagrams")}>
    <h2>{t("Explanatory diagrams")}</h2>
    {diagrams.map(diagram => <Diagram key={diagram.proposal.id} diagram={diagram} />)}
  </section>;
}
