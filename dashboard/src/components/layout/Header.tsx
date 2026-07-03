"use client";

import { usePathname } from "next/navigation";
import styles from "./layout.module.css";
import { Bell, LogOut } from "lucide-react";

export default function Header() {
  const pathname = usePathname();
  
  // Format pathname into a readable title
  const getPageTitle = () => {
    if (pathname === "/") return "Overview";
    const path = pathname.split("/")[1];
    return path.charAt(0).toUpperCase() + path.slice(1);
  };

  return (
    <header className={styles.header}>
      <h1 className={styles.headerTitle}>{getPageTitle()}</h1>
      
      <div className={styles.headerRight}>
        <div className={styles.tenantBadge}>
          <div className={styles.tenantIndicator} />
          <span>ABC Logistics (Active)</span>
        </div>
        
        <button className="btn-secondary" style={{ padding: "0.5rem" }} title="Notifications">
          <Bell size={18} />
        </button>
        <button className="btn-secondary" style={{ padding: "0.5rem" }} title="Logout">
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}
