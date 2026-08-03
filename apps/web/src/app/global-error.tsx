"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="zh-CN">
      <body>
        <main role="alert" className="m-token-2xl rounded-token-lg border border-error bg-error-subtle p-token-2xl">
          <h1 className="text-2xl font-semibold text-error">平台暂时无法显示</h1>
          <p className="mt-token-sm text-secondary">未产生虚假成功，也不会覆盖已有内容。</p>
          <button type="button" onClick={reset} className="mt-token-lg h-control-md rounded-token-md bg-brand-primary px-token-lg text-sm font-medium text-inverse">
            重新加载
          </button>
        </main>
      </body>
    </html>
  );
}
