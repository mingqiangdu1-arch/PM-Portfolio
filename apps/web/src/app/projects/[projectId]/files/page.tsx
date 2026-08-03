import { AppShell } from "@/components/app-shell";
import { FilePanel } from "@/features/files/file-panel";
import type { Scenario } from "@/lib/api/ports";
export default async function FilesPage({ params, searchParams }: { params: Promise<{ projectId: string }>; searchParams: Promise<{ state?: Scenario }> }) { const { projectId } = await params; const { state = "ready" } = await searchParams; return <AppShell projectId={projectId}><FilePanel projectId={projectId} scenario={state} /></AppShell>; }
