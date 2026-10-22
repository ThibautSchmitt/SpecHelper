import { Suspense } from "react";
import { WorkItemForm } from "@/components/work-item-form";

export default function Home() {
  return <Suspense><WorkItemForm /></Suspense>;
}
