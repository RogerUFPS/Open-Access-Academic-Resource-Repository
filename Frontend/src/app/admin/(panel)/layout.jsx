import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import AdminLayout from "@/shared/layouts/AdminLayout";
import AccountsGateway from "@/shared/components/AccountsGateway";
import { apiClient, pendingAccountStep } from "@/shared/services/apiClient";
import { getUserDisplayName } from "@/shared/services/userService";

export default async function AdminRouteLayout({ children }) {
  const store = await cookies();
  const session = store.get("sessionid")?.value;
  if (!session) redirect("/admin/login");

  let user;
  try {
    user = await apiClient.get("/api/accounts/auth/me/", {}, {
      headers: { Cookie: `sessionid=${session}` },
      cache: "no-store",
      signal: AbortSignal.timeout(60000),
      redirect: "error",
    });
  } catch (error) {
    if (![401, 403].includes(error.status)) throw error;
  }

  // Password changes and superadmin MFA are completed on the login screen.
  if (!user || pendingAccountStep(user)) redirect("/admin/login");

  return <AccountsGateway initialUser={user}><AdminLayout userName={getUserDisplayName(user)}>{children}</AdminLayout></AccountsGateway>;
}
