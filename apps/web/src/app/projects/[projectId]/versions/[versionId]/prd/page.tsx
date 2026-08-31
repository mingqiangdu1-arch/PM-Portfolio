import { AppShell } from "@/components/app-shell";
import { PrdWorkbench } from "@/features/prds/prd-workbench";

export default async function PrdPage({ params }: { params: Promise<{ projectId: string; versionId: string }> }) {
  const { projectId, versionId } = await params;
  return <AppShell projectId={projectId}><PrdWorkbench projectId={projectId} projectVersionId={versionId} /></AppShell>;
}
