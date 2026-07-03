"use client";

import React from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import styles from "./layout.module.css";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className={styles.layoutWrapper}>
      <Sidebar />
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
  );
}
