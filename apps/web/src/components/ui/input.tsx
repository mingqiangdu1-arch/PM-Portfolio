import { forwardRef, type InputHTMLAttributes } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className = "", invalid = false, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={`h-control-md w-full rounded-token-md border bg-surface px-token-md text-sm text-primary placeholder:text-muted disabled:cursor-not-allowed disabled:bg-subtle ${invalid ? "border-error" : "border-default"} ${className}`}
      {...props}
    />
  );
});
