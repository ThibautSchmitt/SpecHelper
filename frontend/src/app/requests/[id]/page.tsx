import { WorkItemDetail } from "@/components/work-item-detail";

export default function RequestPage(props: { params: Promise<{ id: string }> }) {
  return <WorkItemDetail {...props} />;
}
