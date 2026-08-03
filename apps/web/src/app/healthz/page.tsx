import { AppShell } from "@/components/app-shell";
import { getPublicAppEnvironment } from "@/config/public-env";
import { ApiHealthStatus } from "@/features/health/api-health-status";

export default function HealthPage() {
  const environment = getPublicAppEnvironment();
  return (
    <AppShell showLogout={false}>
      <section aria-labelledby="health-title" className="max-w-xl rounded-token-lg border border-default bg-surface p-token-2xl">
        <p className="text-sm font-medium text-success">● Web 进程可用</p>
        <h1 id="health-title" className="mt-token-sm text-2xl font-semibold">Frontend health</h1>
        <dl className="mt-token-lg grid grid-cols-[auto_1fr] gap-x-token-lg gap-y-token-sm text-sm">
          <dt className="text-muted">状态</dt><dd>healthy</dd>
          <dt className="text-muted">环境</dt><dd>{environment}</dd>
          <dt className="text-muted">API 契约</dt><dd>Review 冻结契约已生成</dd>
        </dl>
        <ApiHealthStatus />
      </section>
    </AppShell>
  );
}
