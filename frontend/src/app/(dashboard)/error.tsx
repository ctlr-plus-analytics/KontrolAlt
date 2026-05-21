/**
 * Error boundary — catches errors in dashboard routes.
 */
"use client";

import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/Button";

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="max-w-md rounded-xl border border-[#E8E4DC] bg-white p-8 text-center shadow-sm">
        <AlertTriangle
          size={48}
          className="mx-auto mb-4 text-[#E6A817]"
        />
        <h2 className="mb-2 text-lg font-semibold text-[#1A1A2E]">
          Something went wrong
        </h2>
        <p className="mb-6 text-sm text-[#6B6B6B]">
          {error.message || "An unexpected error occurred. Please try again."}
        </p>
        <Button variant="accent" onClick={reset}>
          Try Again
        </Button>
      </div>
    </div>
  );
}
