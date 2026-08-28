/**
 * useAuth hook.
 *
 * Provides a clean interface to authentication state and operations.
 * Wraps the Zustand store and auth service calls together.
 *
 * Usage:
 *   const { user, isAuthenticated, login, logout, register } = useAuth();
 */

"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import * as authService from "@/services/auth.service";
import { useAuthStore } from "@/store/auth.store";
import type { LoginRequest, RegisterRequest } from "@/types";

export function useAuth() {
  const router = useRouter();
  const { user, isAuthenticated, isInitializing, setAuth, clearAuth } =
    useAuthStore();

  const login = useCallback(
    async (data: LoginRequest) => {
      const response = await authService.login(data);
      const { access_token, refresh_token, user: authUser } = response.data;
      setAuth(authUser, access_token, refresh_token);
      return authUser;
    },
    [setAuth],
  );

  const register = useCallback(
    async (data: RegisterRequest) => {
      const response = await authService.register(data);
      return response.data;
    },
    [],
  );

  const logout = useCallback(async () => {
    const refreshToken =
      typeof window !== "undefined"
        ? sessionStorage.getItem("intelliflow_refresh_token")
        : null;

    try {
      if (refreshToken) {
        await authService.logout({ refresh_token: refreshToken });
      }
    } finally {
      clearAuth();
      router.push("/login");
    }
  }, [clearAuth, router]);

  return {
    user,
    isAuthenticated,
    isInitializing,
    login,
    register,
    logout,
  };
}
