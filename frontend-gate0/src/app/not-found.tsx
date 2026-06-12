/**
 * 404 Not Found page.
 */
import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F7F4EE] px-4">
      <div className="max-w-md rounded-xl border border-[#E8E4DC] bg-white p-8 text-center shadow-sm">
        <h1 className="mb-2 text-4xl font-bold text-[#1A1A2E]">404</h1>
        <h2 className="mb-2 text-lg font-semibold text-[#1A1A2E]">
          Page Not Found
        </h2>
        <p className="mb-6 text-sm text-[#6B6B6B]">
          The page you are looking for does not exist or has been moved.
        </p>
        <Link
          href="/"
          className="inline-flex items-center justify-center rounded-lg bg-[#1A1A2E] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#2A2A3E]"
        >
          Go to Dashboard
        </Link>
      </div>
    </div>
  );
}
