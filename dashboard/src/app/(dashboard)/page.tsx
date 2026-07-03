"use client";

import { useEffect, useState } from "react";
import SuperAdminView from "@/components/dashboard/SuperAdminView";
import TenantAdminView from "@/components/dashboard/TenantAdminView";
import { Loader2 } from "lucide-react";

export default function DashboardHome() {
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    // Read the role from localStorage on the client side
    const savedRole = localStorage.getItem("user_role");
    setRole(savedRole || "tenant_admin"); // default fallback
  }, []);

  if (!role) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "50vh" }}>
        <Loader2 className="animate-spin" size={32} color="var(--accent-primary)" />
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      {role === "super_admin" ? <SuperAdminView /> : <TenantAdminView />}
    </div>
  );
}
