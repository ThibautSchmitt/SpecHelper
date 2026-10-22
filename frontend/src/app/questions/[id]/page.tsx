import { WorkItemDetail } from "@/components/work-item-detail";

export default function QuestionPage(props: { params: Promise<{ id: string }> }) {
  return <WorkItemDetail {...props} workflow="question" />;
}
