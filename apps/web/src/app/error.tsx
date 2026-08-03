"use client";

import { useEffect } from "react";

export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return (
    <section role="alert" className="m-token-2xl rounded-token-lg border border-error bg-error-subtle p-token-2xl text-primary">
      <p className="font-semibold text-error">页面加载失败</p>
      <p className="mt-token-sm text-sm text-secondary">当前内容未被修改，可以安全重试。</p>
      <button type="button" onClick={reset} className="mt-token-lg h-control-md rounded-token-md bg-brand-primary px-token-lg text-sm font-medium text-inverse">
        重试
      </button>
    </section>
  );
}
