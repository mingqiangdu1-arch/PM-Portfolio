import type { ReactNode } from "react";
import Link from "next/link";
import { LogoutButton } from "@/features/identity/logout-button";
import { SessionRecoveryRedirect } from "@/features/identity/session-recovery-redirect";
import { SiteFooter } from "@/components/site-footer";

export function AppShell({ children, projectId, showLogout = true }: { children: ReactNode; projectId?: string; showLogout?: boolean }) {
  return (
    <div className="flex min-h-screen flex-col bg-canvas text-primary">
      <SessionRecoveryRedirect />
      <header className="border-b border-default bg-surface">
        <div className="mx-auto flex min-h-control-lg max-w-content flex-wrap items-center justify-between gap-token-md px-token-md py-token-sm sm:px-token-xl">
          <div>
            <p className="text-sm font-semibold">AI 产品设计与验证平台</p>
            <p className="text-xs text-muted">MVP5 · AI 产品设计与验证闭环</p>
          </div>
          <nav aria-label="主导航" className="flex flex-wrap items-center gap-token-sm text-sm">
            <Link className="rounded-token-md px-token-sm py-token-xs text-primary-action hover:bg-primary-subtle" href="/projects">项目</Link>
            {projectId ? <Link className="rounded-token-md px-token-sm py-token-xs text-primary-action hover:bg-primary-subtle" href={`/projects/${projectId}/files`}>资料</Link> : null}
            {projectId ? <Link className="rounded-token-md px-token-sm py-token-xs text-primary-action hover:bg-primary-subtle" href={`/projects/${projectId}/versions`}>版本</Link> : null}
            {showLogout ? <LogoutButton /> : null}
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-content flex-1 px-token-md py-token-xl sm:px-token-xl sm:py-token-3xl">{children}</main>
      <SiteFooter />
    </div>
  );
}
