import { Suspense } from "react";
import { AnalysesList } from "@/components/analyses-list";

export default function AnalysesPage() {
  return <Suspense><AnalysesList /></Suspense>;
}
