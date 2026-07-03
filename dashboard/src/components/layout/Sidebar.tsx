"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./layout.module.css";
import {
  LayoutDashboard,
  PhoneCall,
  History,
  BarChart3,
  Truck,
  Users,
  DollarSign,
  Settings,
  Shield,
} from "lucide-react";
import { useEffect, useState } from "react";

export default function Sidebar() {
  const pathname = usePathname();
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      setRole(localStorage.getItem("user_role"));
    }
  }, []);

  const navItems = [
    { name: "Overview", href: "/", icon: LayoutDashboard },
    { name: "Live Monitor", href: "/live", icon: PhoneCall },
    { name: "Call History", href: "/history", icon: History },
    { name: "Analytics", href: "/analytics", icon: BarChart3 },
    { name: "Loads", href: "/loads", icon: Truck },
    { name: "Drivers", href: "/drivers", icon: Users },
    { name: "Rates", href: "/rates", icon: DollarSign },
    { name: "Settings", href: "/settings", icon: Settings },
    { name: "Super Admin", href: "/admin", icon: Shield, requireRole: "super_admin" },
  ];

  const visibleNavItems = navItems.filter(item => !item.requireRole || item.requireRole === role);

  return (
    <aside className={styles.sidebar}>
      <div className={styles.logoContainer}>
        <span className={`${styles.logoText} gradient-text`}>Nexus Dispatch</span>
      </div>
      
      <nav className={styles.navMenu}>
        {visibleNavItems.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`${styles.navItem} ${isActive ? styles.navItemActive : ""}`}
            >
              <Icon className={styles.navIcon} />
              {item.name}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
