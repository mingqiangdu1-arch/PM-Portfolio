"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { frontendApi } from "@/lib/api/frontend-api";
const safeReturnTo = (value: string | null | undefined) => value?.startsWith("/") && !value.startsWith("//") ? value : "/projects";
export function AuthForm({ mode, returnTo }: { mode: "login" | "register"; returnTo?: string | null }) {
  const router = useRouter(); const [displayName, setDisplayName] = useState(""); const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { if (mode === "login") await frontendApi.identity.login({ email, password }); else await frontendApi.identity.register({ displayName, email, password }); router.push(safeReturnTo(returnTo)); } catch (reason) { setError(reason instanceof Error ? reason.message : "认证失败，请重试。"); } finally { setBusy(false); } }
  return <form onSubmit={submit} className="panel mx-auto max-w-md space-y-token-lg" aria-labelledby="auth-title">
    <div><p className="text-sm font-medium text-ai">FE-101</p><h1 id="auth-title" className="mt-token-xs text-2xl font-semibold">{mode === "login" ? "登录" : "创建账户"}</h1><p className="mt-token-xs text-sm text-secondary">认证成功后返回原目标；敏感提交不会自动重放。</p></div>
    {error ? <div role="alert" className="status-banner bg-error-subtle text-error">{error}</div> : null}
    {mode === "register" ? <label className="block"><span className="field-label">显示名称</span><Input name="displayName" value={displayName} onChange={(e) => setDisplayName(e.target.value)} autoComplete="name" required /></label> : null}
    <label className="block"><span className="field-label">邮箱</span><Input name="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required /></label>
    <label className="block"><span className="field-label">密码</span><Input name="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "register" ? 12 : undefined} required /></label>
    <Button className="w-full" loading={busy} type="submit">{mode === "login" ? "登录" : "注册并进入"}</Button>
    <p className="text-center text-sm text-secondary">{mode === "login" ? <>没有账户？ <Link className="text-primary-action" href="/register">注册</Link></> : <>已有账户？ <Link className="text-primary-action" href="/login">登录</Link></>}</p>
  </form>;
}
