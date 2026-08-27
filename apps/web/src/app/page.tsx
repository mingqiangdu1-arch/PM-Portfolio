import { AppShell } from "@/components/app-shell";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function FoundationPage() {
  return (
    <AppShell>
      <section aria-labelledby="foundation-title" className="max-w-3xl">
        <p className="mb-token-sm text-sm font-medium text-ai">MVP5 · 生产主流程</p>
        <h1 id="foundation-title" className="text-3xl font-semibold tracking-tight">
          AI 产品设计与验证闭环
        </h1>
        <p className="mt-token-md text-secondary">
          从 Requirement 与真实 AI 澄清开始，经人工确认形成 Baseline，并持续推进 PRD、Design Review、Implementation Plan、Confirmation、Validation、Issue 处置与版本迭代。
        </p>
        <div className="mt-token-2xl rounded-token-lg border border-default bg-surface p-token-2xl">
          <div className="mt-token-lg flex flex-wrap gap-token-sm">
            <Link href="/login"><Button type="button" variant="secondary">登录</Button></Link>
            <Link href="/projects"><Button type="button">进入项目中心</Button></Link>
          </div>
        </div>
      </section>
    </AppShell>
  );
}
