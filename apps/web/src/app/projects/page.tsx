import { AppShell } from "@/components/app-shell";
import { ProjectList } from "@/features/projects/project-list";
import type { Scenario } from "@/lib/api/ports";
export default async function ProjectsPage({ searchParams }: { searchParams: Promise<{ state?: Scenario }> }) { const { state = "ready" } = await searchParams; return <AppShell><ProjectList scenario={state} /></AppShell>; }
