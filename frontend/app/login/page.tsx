"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { saveTokens } from "@/lib/auth";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  
  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [generalError, setGeneralError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setEmailError("");
    setPasswordError("");
    setGeneralError("");

    let hasError = false;

    if (!email) {
      setEmailError("Email address is required.");
      hasError = true;
    }
    if (!password) {
      setPasswordError("Password is required.");
      hasError = true;
    }

    if (hasError) return;

    setIsLoading(true);

    try {
      const api = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
      const response = await fetch(`${api}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        setGeneralError(response.status === 401 ? "Invalid email or password." : "Unable to sign in. Please try again.");
        return;
      }
      saveTokens(await response.json());
      window.dispatchEvent(new Event("suitespot-auth-change"));
      const next = new URLSearchParams(window.location.search).get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") && !next.includes("\\") ? next : "/hotels");
    } catch (err) {
      setGeneralError("Invalid email or password. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-4rem)] w-full bg-canvas">
      
      {/* Left Side: Form */}
      <div className="flex flex-1 flex-col justify-center px-4 py-12 sm:px-6 lg:flex-none lg:w-1/2 xl:w-5/12 border-r border-line">
        <div className="mx-auto w-full max-w-sm">
          <Card className="border-transparent shadow-none bg-transparent sm:border-line sm:bg-surface sm:shadow-sm">
            <CardHeader className="space-y-1 text-center">
              <CardTitle className="text-2xl font-semibold tracking-tight text-ink">
                Welcome Back
              </CardTitle>
              <CardDescription className="text-muted">
                Enter your credentials to access your LikeHome account
              </CardDescription>
            </CardHeader>

            <form onSubmit={handleSubmit}>
              <CardContent className="space-y-4">
                {generalError && (
                  <div className="p-3 text-sm text-danger bg-danger-soft border border-danger/20 rounded-control">
                    {generalError}
                  </div>
                )}

                <div className="space-y-1.5 text-left">
                  <label className="text-xs font-bold text-muted uppercase tracking-wider">
                    Email
                  </label>
                  <Input 
                    type="email" 
                    placeholder="name@example.com" 
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      if (emailError) setEmailError("");
                    }}
                    aria-invalid={!!emailError}
                  />
                  {emailError && (
                    <p className="text-xs text-danger mt-1">{emailError}</p>
                  )}
                </div>

                <div className="space-y-1.5 text-left">
                  <label className="text-xs font-bold text-muted uppercase tracking-wider">
                    Password
                  </label>
                  <Input 
                    type="password" 
                    placeholder="••••••••" 
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      if (passwordError) setPasswordError("");
                    }}
                    aria-invalid={!!passwordError}
                  />
                  {passwordError && (
                    <p className="text-xs text-danger mt-1">{passwordError}</p>
                  )}
                </div>

                <Button type="submit" disabled={isLoading} className="w-full h-11 mt-2 font-bold">
                  {isLoading ? "Signing in..." : "Sign In"}
                </Button>
              </CardContent>
            </form>

            <CardFooter className="justify-center border-t border-line py-5">
              <p className="text-sm text-muted">
                Don&apos;t have an account?{" "}
                <Link href="/register" className="font-bold text-ink hover:text-accent transition-colors">
                  Sign Up
                </Link>
              </p>
            </CardFooter>
          </Card>
        </div>
      </div>

      {/* Right Side: Wood Slat Imagery */}
      <div className="relative hidden w-0 flex-1 lg:block bg-surface-muted">
        <img
          className="absolute inset-0 h-full w-full object-cover"
          src="https://slats.co/cdn/shop/collections/wood-slat-acoustic-panels-394065.jpg?v=1782954344&width=2048"
          alt="Vertical wood slat acoustic panels"
        />
        {/* Very subtle overlay to blend the image warmth with the UI */}
        <div className="absolute inset-0 bg-ink/5 mix-blend-multiply" />
      </div>

    </div>
  );
}