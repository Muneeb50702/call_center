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

  const handleLogout = () => {
    // Clear localStorage
    localStorage.removeItem("access_token");
    localStorage.removeItem("user_role");
    // Clear cookie (if it exists)
    document.cookie = "token=; path=/; expires=Thu, 01 Jan 1970 00:00:01 GMT;";
    // Redirect to login
    window.location.href = "/login";
  };

  return (
    <header className={styles.header}>
      <h1 className={styles.headerTitle}>{getPageTitle()}</h1>
      
      <div className={styles.headerRight}>
        <button className="btn-secondary" style={{ padding: "0.5rem" }} title="Notifications">
          <Bell size={18} />
        </button>
        <button 
          className="btn-secondary" 
          style={{ padding: "0.5rem" }} 
          title="Logout"
          onClick={handleLogout}
        >
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}
