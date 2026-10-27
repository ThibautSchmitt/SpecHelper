import { WorkItemDetail } from "@/components/work-item-detail";

export default function AnalysisPage({ params }: { params: Promise<{ id: string }> }) {
  return <WorkItemDetail params={params} unified />;
}
