"use client";

import React from "react";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

interface DashboardLayoutProps {
  children: React.ReactNode;
  title?: string;
  description?: string;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({
  children,
  title,
  description,
}) => {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        background: "var(--ink-90)",
        color: "#e2e8f0",
      }}
    >
      <Sidebar />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <Header title={title} description={description} />
        <main
          style={{
            flex: 1,
            padding: "40px 44px",
            overflowY: "auto",
            maxWidth: "100%",
          }}
        >
          {children}
        </main>
      </div>
    </div>
  );
};
