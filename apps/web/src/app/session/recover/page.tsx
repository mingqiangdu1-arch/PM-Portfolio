import { AppShell } from "@/components/app-shell";
import { SessionRecovery } from "@/features/identity/session-recovery";
export default async function RecoverPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) { const { returnTo = "/projects" } = await searchParams; return <AppShell><div className="mx-auto max-w-xl"><SessionRecovery returnTo={returnTo} /></div></AppShell>; }
