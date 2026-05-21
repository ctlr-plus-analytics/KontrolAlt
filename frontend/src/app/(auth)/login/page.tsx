/**
 * Login page — authenticates users via Supabase Auth.
 * Client component with email/password form.
 */
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const result = await signIn(email, password);

    if (result.error) {
      setError("Invalid credentials. Please try again.");
      setLoading(false);
    } else {
      router.push("/");
    }
  };

  return (
    <div className="rounded-xl border border-[#E8E4DC] bg-[#F7F4EE] p-8 shadow-lg">
      <h2 className="mb-1 text-xl font-semibold tracking-tight text-[#1A1A2E]">
        Welcome back
      </h2>
      <p className="mb-6 text-sm text-[#6B6B6B]">
        Sign in to your account
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          id="email"
          label="Email"
          type="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
        />

        <Input
          id="password"
          label="Password"
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="current-password"
        />

        {error && (
          <div className="rounded-lg bg-[#B22222]/10 px-4 py-3 text-sm text-[#B22222]">
            {error}
          </div>
        )}

        <Button
          type="submit"
          variant="accent"
          size="lg"
          loading={loading}
          className="w-full"
        >
          Sign In
        </Button>
      </form>
    </div>
  );
}
