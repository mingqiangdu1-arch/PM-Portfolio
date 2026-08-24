import { AuthForm } from "@/features/identity/auth-form";
import { SiteFooter } from "@/components/site-footer";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ returnTo?: string; loggedOut?: string }> }) {
  const params = await searchParams;
  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <main className="flex-1 px-token-md py-token-3xl">
        <AuthForm mode="login" returnTo={params.returnTo} />
        {params.loggedOut ? <p role="status" className="mx-auto mt-token-md max-w-md text-center text-sm text-success">已安全退出。</p> : null}
      </main>
      <SiteFooter />
    </div>
  );
}
