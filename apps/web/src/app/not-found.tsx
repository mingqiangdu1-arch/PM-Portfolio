import { AppShell } from "@/components/app-shell";
import Link from "next/link";

export default function NotFound() {
  return (
    <AppShell>
      <section aria-labelledby="not-found-title" className="max-w-xl rounded-token-lg border border-default bg-surface p-token-2xl">
        <p className="text-sm font-medium text-warning">404 · 页面不存在</p>
        <h1 id="not-found-title" className="mt-token-sm text-2xl font-semibold">无法找到这个入口</h1>
        <p className="mt-token-md text-secondary">请检查地址，或返回平台首页继续。</p>
        <Link href="/" className="mt-token-lg inline-flex h-control-md items-center rounded-token-md bg-brand-primary px-token-lg text-sm font-medium text-inverse">
          返回首页
        </Link>
      </section>
    </AppShell>
  );
}
