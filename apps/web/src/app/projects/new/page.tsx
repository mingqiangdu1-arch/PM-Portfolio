import { AppShell } from "@/components/app-shell";
import { CreateProjectForm } from "@/features/projects/create-project-form";
import type { Scenario } from "@/lib/api/ports";
export default async function NewProjectPage({ searchParams }: { searchParams: Promise<{ state?: Scenario }> }) { const { state = "ready" } = await searchParams; return <AppShell><CreateProjectForm scenario={state} /></AppShell>; }
