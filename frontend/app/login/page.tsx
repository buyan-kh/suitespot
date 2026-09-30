"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  
  // Changed to individual field errors for inline surfacing
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

    // Inline validation checks
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
      // TODO: Connect to Vincent's POST /login endpoint
      console.log("Submitting login for:", email);
      
      // Simulate network request
      await new Promise((resolve) => setTimeout(resolve, 1000));
    } catch (err) {
      setGeneralError("Invalid email or password. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-12">
      <Card className="w-full max-w-md border-stone-200/80 shadow-sm">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-2xl font-semibold tracking-tight text-stone-900">
            Welcome Back
          </CardTitle>
          <CardDescription className="text-stone-500">
            Enter your credentials to access your LikeHome account
          </CardDescription>
        </CardHeader>

        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            {/* General Error Banner (for server/auth failures) */}
            {generalError && (
              <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md">
                {generalError}
              </div>
            )}

            {/* Email Field with Inline Error */}
            <div className="space-y-1.5 text-left">
              <label className="text-xs font-medium text-stone-600 uppercase tracking-wider">
                Email
              </label>
              <Input 
                type="email" 
                placeholder="name@example.com" 
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (emailError) setEmailError(""); // Clear error on type
                }}
                className={`border-stone-300 focus-visible:ring-stone-900 ${
                  emailError ? "border-red-500 focus-visible:ring-red-500" : ""
                }`} 
              />
              {emailError && (
                <p className="text-xs text-red-500 mt-1">{emailError}</p>
              )}
            </div>

            {/* Password Field with Inline Error */}
            <div className="space-y-1.5 text-left">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-stone-600 uppercase tracking-wider">
                  Password
                </label>
              </div>
              <Input 
                type="password" 
                placeholder="••••••••" 
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (passwordError) setPasswordError(""); // Clear error on type
                }}
                className={`border-stone-300 focus-visible:ring-stone-900 ${
                  passwordError ? "border-red-500 focus-visible:ring-red-500" : ""
                }`} 
              />
              {passwordError && (
                <p className="text-xs text-red-500 mt-1">{passwordError}</p>
              )}
            </div>

            <Button type="submit" disabled={isLoading} className="w-full h-11 mt-2 font-medium">
              {isLoading ? "Signing in..." : "Sign In"}
            </Button>
          </CardContent>
        </form>

        <CardFooter className="justify-center border-t border-stone-100 py-4">
          <p className="text-sm text-stone-500">
            Don&apos;t have an account?{" "}
            <Link href="/register" className="font-medium text-stone-900 hover:underline">
              Sign Up
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  );
}