import React from "react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen w-full flex items-center justify-center p-4 bg-gradient-to-br from-slate-50 via-gray-100 to-blue-50 dark:from-slate-950 dark:via-gray-900 dark:to-blue-950/20">
      <div className="w-full flex items-center justify-center">
        {children}
      </div>
    </div>
  );
}
