import type { Metadata } from "next";
import Link from "next/link";
import RegisterForm from "@/components/auth/RegisterForm";

export const metadata: Metadata = {
  title: "Create an account | LikeHome",
};

export default function RegisterPage() {
  return (
    <div className="mx-auto flex w-full max-w-md flex-col px-4 py-16 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight text-ink">Create your account</h1>
      <p className="mt-2 text-sm text-muted">
        Book stays, manage reservations, and earn reward points.
      </p>

      <div className="mt-8 rounded-card border border-line bg-surface p-6 shadow-sm">
        <RegisterForm />
      </div>

      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-ink underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </div>
  );
}