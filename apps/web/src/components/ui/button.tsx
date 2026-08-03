import { forwardRef, type ButtonHTMLAttributes } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
}

const variants: Record<ButtonVariant, string> = {
  primary: "border-transparent bg-brand-primary text-inverse hover:bg-brand-primary-hover disabled:bg-brand-primary-disabled disabled:text-secondary",
  secondary: "border-default bg-surface text-primary hover:bg-subtle",
  ghost: "border-transparent bg-transparent text-primary-action hover:bg-primary-subtle",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className = "", variant = "primary", loading = false, disabled, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={`inline-flex h-control-md items-center justify-center gap-token-sm rounded-token-md border px-token-lg text-sm font-medium transition-colors disabled:cursor-not-allowed ${variants[variant]} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <span aria-hidden="true">◌</span> : null}
      <span>{children}</span>
    </button>
  );
});
