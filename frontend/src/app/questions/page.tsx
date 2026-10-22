import { Suspense } from "react";
import { WorkItemForm } from "@/components/work-item-form";

export default function QuestionsPage() {
  return <Suspense><WorkItemForm workflow="question" /></Suspense>;
}
