/**
 * Providers — client component wrapping children with context providers.
 */
"use client";

interface ProvidersProps {
  children: React.ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  return <>{children}</>;
}
