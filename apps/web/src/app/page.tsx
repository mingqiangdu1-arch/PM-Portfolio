import { AppShell } from "@/components/app-shell";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function FoundationPage() {
  return (
    <AppShell>
      <section aria-labelledby="foundation-title" className="max-w-3xl">
        <p className="mb-token-sm text-sm font-medium text-ai">Sprint 1 · 第一波</p>
        <h1 id="foundation-title" className="text-3xl font-semibold tracking-tight">
          Identity、Project 与 Version
        </h1>
        <p className="mt-token-md text-secondary">
          路由、页面状态、共享 Client 边界与 Mock Adapter 已进入实现；真实 API Client 等待 OpenAPI 冻结。
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
