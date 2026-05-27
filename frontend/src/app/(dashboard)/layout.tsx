import { TopBar } from "@/components/layout/TopBar";

export default function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#F7F4EE]">
      <TopBar />
      <main className="flex-1 overflow-hidden">
        {children}
      </main>
    </div>
  );
}
