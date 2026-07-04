"use client";

import React, { useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import styles from "./layout.module.css";
import { ToastProvider } from "@/components/ui/Toast";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);

  // Auto-collapse on mobile
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) setCollapsed(true);
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <ToastProvider>
      <div className={styles.layoutWrapper}>
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
        <div className={styles.mainContent}>
          <Header />
          <div className={styles.bgGlow} />
          <main className={styles.pageContainer}>
            <div className="animate-fade-in" style={{ position: "relative", zIndex: 1 }}>
              {children}
            </div>
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}
