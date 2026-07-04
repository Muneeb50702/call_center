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
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { useEffect, useState } from "react";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
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
    <aside className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : ""}`}>
      <div className={styles.logoContainer}>
        {!collapsed && <span className={`${styles.logoText} gradient-text`}>Nexus Dispatch</span>}
        <button
          onClick={onToggle}
          className={styles.collapseBtn}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
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
              title={collapsed ? item.name : undefined}
            >
              <Icon className={styles.navIcon} />
              {!collapsed && <span>{item.name}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Bottom section — version */}
      {!collapsed && (
        <div className={styles.sidebarFooter}>
          <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)", letterSpacing: "0.05em" }}>
            NEXUS v1.0.0
          </span>
        </div>
      )}
    </aside>
  );
}
