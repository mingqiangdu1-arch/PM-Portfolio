import { AppShell } from "@/components/app-shell";
import { VersionDetail } from "@/features/projects/version-manager";
import type { Scenario } from "@/lib/api/ports";
export default async function VersionPage({ params, searchParams }: { params: Promise<{ projectId: string; versionId: string }>; searchParams: Promise<{ state?: Scenario }> }) { const { projectId, versionId } = await params; const { state = "ready" } = await searchParams; return <AppShell projectId={projectId}><VersionDetail projectId={projectId} versionId={versionId} scenario={state} /></AppShell>; }
