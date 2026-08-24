import { AppShell } from "@/components/app-shell";
import { ImplementationPlanWorkspace } from "@/features/implementation-plans/implementation-plan-workspace";

export default async function ImplementationPlanPage({ params, searchParams }: { params: Promise<{ projectId: string; versionId: string }>; searchParams?: Promise<{ state?: string }> }) {
  const { projectId, versionId } = await params;
  const query = await searchParams;
  const scenario = ["ready", "forbidden", "conflict", "failure"].includes(query?.state ?? "") ? query?.state as "ready" | "forbidden" | "conflict" | "failure" : "ready";
  return <AppShell projectId={projectId}><ImplementationPlanWorkspace projectId={projectId} projectVersionId={versionId} scenario={scenario} /></AppShell>;
}
