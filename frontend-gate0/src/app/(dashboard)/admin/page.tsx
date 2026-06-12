import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { AdminControlPanel } from "@/components/admin/AdminControlPanel";

function isAdminUser(user: {
  app_metadata?: Record<string, unknown> | null;
  user_metadata?: Record<string, unknown> | null;
}): boolean {
  const appMetadata = user.app_metadata ?? {};
  const userMetadata = user.user_metadata ?? {};
  const appRole = appMetadata.role;
  const appAdmin = appMetadata.is_admin;
  const userRole = userMetadata.role;
  const userAdmin = userMetadata.is_admin;
  return (
    appRole === "admin" ||
    appAdmin === true ||
    appAdmin === "true" ||
    userRole === "admin" ||
    userAdmin === true ||
    userAdmin === "true"
  );
}

export default async function AdminPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user || !isAdminUser(user)) {
    redirect("/");
  }

  return (
    <div className="h-full overflow-y-auto p-6 scrollbar-thin">
      <AdminControlPanel />
    </div>
  );
}
