import { AppShell } from "@/components/app-shell";
import { ConfirmationWorkspace } from "@/features/confirmation/confirmation-workspace";

export default async function ConfirmationPage({ params, searchParams }: { params: Promise<{ projectId: string; versionId: string }>; searchParams?: Promise<{ state?: string; planId?: string }> }) {
  const { projectId, versionId } = await params;
  const query = await searchParams;
  const scenario = ["ready", "forbidden", "conflict", "failure"].includes(query?.state ?? "") ? query?.state as "ready" | "forbidden" | "conflict" | "failure" : "ready";
  return <AppShell projectId={projectId}><ConfirmationWorkspace projectId={projectId} planId={query?.planId} projectVersionId={versionId} scenario={scenario} /></AppShell>;
}
