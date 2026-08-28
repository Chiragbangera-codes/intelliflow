"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth.store";
import { Badge } from "@/components/ui/Badge";

interface HeaderProps {
  title?: string;
  description?: string;
}

export const Header: React.FC<HeaderProps> = ({ title, description }) => {
  const router = useRouter();
  const { user, clearAuth } = useAuthStore();

  const handleLogout = () => {
    clearAuth();
    router.push("/login");
  };

  const getRoleVariant = (role?: string) => {
    switch (role) {
      case "admin":
        return "primary";
      case "hr":
        return "info";
      case "manager":
        return "warning";
      case "finance":
        return "success";
      default:
        return "neutral";
    }
  };

  return (
    <header className="h-16 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-8 flex items-center justify-between sticky top-0 z-10">
      <div>
        {title && (
          <h1 className="text-xl font-bold text-gray-900 dark:text-white tracking-tight">{title}</h1>
        )}
        {description && (
          <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
        )}
      </div>

      <div className="flex items-center gap-4">
        {user && (
          <div className="flex items-center gap-3">
            <Badge variant={getRoleVariant(user.role)} size="sm">
              {user.role}
            </Badge>

            <div className="hidden sm:block text-right">
              <p className="text-sm font-semibold text-gray-900 dark:text-white leading-tight">
                {user.first_name} {user.last_name}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{user.email}</p>
            </div>

            <button
              onClick={handleLogout}
              className="px-3 py-1.5 text-xs font-medium text-rose-600 hover:text-white hover:bg-rose-600 border border-rose-200 dark:border-rose-900/40 rounded-xl transition-all shadow-2xs"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
