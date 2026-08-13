import { AppShell } from "@/components/app-shell";
import { RequirementWorkspace } from "@/features/requirements/requirement-workspace";

export default async function RequirementsPage({ params }: { params: Promise<{ projectId: string; versionId: string }> }) {
  const { projectId, versionId } = await params;
  return <AppShell projectId={projectId}><RequirementWorkspace projectVersionId={versionId} /></AppShell>;
}
