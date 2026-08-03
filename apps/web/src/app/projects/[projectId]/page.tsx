import { AppShell } from "@/components/app-shell";
import { ProjectOverview } from "@/features/projects/project-overview";
import type { Scenario } from "@/lib/api/ports";
export default async function OverviewPage({ params, searchParams }: { params: Promise<{ projectId: string }>; searchParams: Promise<{ version?: string; created?: string; state?: Scenario }> }) { const { projectId } = await params; const query = await searchParams; return <AppShell projectId={projectId}><ProjectOverview projectId={projectId} viewedVersionId={query.version} created={query.created === "1"} scenario={query.state} /></AppShell>; }
