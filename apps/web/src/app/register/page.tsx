import { AuthForm } from "@/features/identity/auth-form";
import { SiteFooter } from "@/components/site-footer";

export default function RegisterPage() {
  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <main className="flex-1 px-token-md py-token-3xl">
        <AuthForm mode="register" />
      </main>
      <SiteFooter />
    </div>
  );
}
