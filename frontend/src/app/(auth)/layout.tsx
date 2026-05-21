/**
 * Auth layout — centered card on navy background.
 */
export default function AuthLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#1A1A2E] px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold tracking-widest text-[#C9A84C]">
            KONTROL_ALT
          </h1>
          <p className="mt-1 text-sm text-[#F7F4EE]/50">
            Intelligence &amp; Discovery Engine
          </p>
        </div>
        {children}
      </div>
    </div>
  );
}
