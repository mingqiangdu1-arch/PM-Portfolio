import { AppShell } from "@/components/app-shell";
import { VersionManager } from "@/features/projects/version-manager";
import type { Scenario } from "@/lib/api/ports";
export default async function VersionsPage({ params, searchParams }: { params: Promise<{ projectId: string }>; searchParams: Promise<{ state?: Scenario }> }) { const { projectId } = await params; const { state = "ready" } = await searchParams; return <AppShell projectId={projectId}><VersionManager projectId={projectId} scenario={state} /></AppShell>; }
