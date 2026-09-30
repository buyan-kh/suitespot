"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

// Task 5.1.1 - registration form. Backend: POST /register (task 5.1.2, David).
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Fields = { email: string; password: string; confirmPassword: string };
type Errors = Partial<Record<keyof Fields | "form", string>>;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validate(f: Fields): Errors {
  const e: Errors = {};
  if (!f.email.trim()) e.email = "Enter your email.";
  else if (!EMAIL_RE.test(f.email.trim())) e.email = "Enter a valid email, like name@example.com.";

  if (!f.password) e.password = "Enter a password.";
  else if (f.password.length < 8) e.password = "Password must be at least 8 characters.";
  else if (!/[A-Za-z]/.test(f.password) || !/\d/.test(f.password))
    e.password = "Password needs at least one letter and one number.";

  if (!f.confirmPassword) e.confirmPassword = "Confirm your password.";
  else if (f.confirmPassword !== f.password) e.confirmPassword = "Passwords don't match.";
  return e;
}

export default function RegisterForm() {
  const router = useRouter();
  const [fields, setFields] = useState<Fields>({ email: "", password: "", confirmPassword: "" });
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);

  function update(name: keyof Fields, value: string) {
    setFields((f) => ({ ...f, [name]: value }));
    if (errors[name]) setErrors((e) => ({ ...e, [name]: undefined }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validate(fields);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: fields.email.trim(), password: fields.password }),
      });

      if (res.ok) {
        router.push("/login");
        return;
      }
      if (res.status === 409) {
        setErrors({ email: "An account with this email already exists." });
      } else {
        const data = await res.json().catch(() => null);
        const detail = typeof data?.detail === "string" ? data.detail : null;
        setErrors({ form: detail ?? "Couldn't create your account. Please try again." });
      }
    } catch {
      setErrors({ form: "Can't reach the server right now. Please try again." });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      {errors.form && (
        <p role="alert" className="rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">
          {errors.form}
        </p>
      )}

      <Field id="email" label="Email" error={errors.email}>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={fields.email}
          onChange={(e) => update("email", e.target.value)}
          aria-invalid={!!errors.email}
          aria-describedby={errors.email ? "email-error" : undefined}
        />
      </Field>

      <Field id="password" label="Password" hint="At least 8 characters, with a letter and a number." error={errors.password}>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          value={fields.password}
          onChange={(e) => update("password", e.target.value)}
          aria-invalid={!!errors.password}
          aria-describedby={errors.password ? "password-error" : "password-hint"}
        />
      </Field>

      <Field id="confirmPassword" label="Confirm password" error={errors.confirmPassword}>
        <Input
          id="confirmPassword"
          type="password"
          autoComplete="new-password"
          value={fields.confirmPassword}
          onChange={(e) => update("confirmPassword", e.target.value)}
          aria-invalid={!!errors.confirmPassword}
          aria-describedby={errors.confirmPassword ? "confirmPassword-error" : undefined}
        />
      </Field>

      <Button type="submit" className="w-full" size="lg" disabled={submitting}>
        {submitting ? "Creating account..." : "Create account"}
      </Button>
    </form>
  );
}

function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}