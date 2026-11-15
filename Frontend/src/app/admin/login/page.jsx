import AdminLoginForm from "@/shared/components/AdminLoginForm";
import AccountsGateway from "@/shared/components/AccountsGateway";
import AdminAuthLayout from "@/shared/layouts/AdminAuthLayout";

export default async function AdminLoginPage({ searchParams }) {
  const { motivo } = await searchParams;
  return (
    <AccountsGateway>
      <AdminAuthLayout>
        <AdminLoginForm reason={typeof motivo === "string" ? motivo : null} />
      </AdminAuthLayout>
    </AccountsGateway>
  )
}
