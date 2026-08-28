/**
 * Zustand authentication store.
 *
 * Manages client-side authentication state:
 *   - Current user profile
 *   - Access token (in-memory — cleared on page reload)
 *   - Authentication status
 *   - Loading / initialization state
 *
 * Token persistence strategy (Milestone 2):
 *   - Access token: window.__intelliflow_access_token (in-memory)
 *   - Refresh token: sessionStorage["intelliflow_refresh_token"]
 *     (survives navigation within the session; cleared on browser close)
 *
 * On page load, the store calls `initialize()` which attempts to restore
 * the session from the stored refresh token by calling /auth/refresh.
 *
 * Production upgrade path:
 *   Move refresh token to HttpOnly Secure SameSite=Strict cookie.
 *   The initialize() flow would then call a /auth/session endpoint instead.
 */

"use client";

import { create } from "zustand";
import * as authService from "@/services/auth.service";
import type { User } from "@/types";

interface AuthState {
  /** The currently authenticated user, or null if not authenticated. */
  user: User | null;

  /** Whether the user is currently authenticated with a valid token. */
  isAuthenticated: boolean;

  /** True while the initial session is being restored from storage. */
  isInitializing: boolean;

  /**
   * Restore authentication state from the stored refresh token.
   * Called once on app mount to handle page refreshes gracefully.
   *
   * Idempotent: safe to call from multiple components — the refresh
   * network request fires exactly once per session. Subsequent calls
   * while the first is in-flight share the same Promise and do not
   * issue additional requests. Once resolved, further calls are no-ops.
   */
  initialize: () => Promise<void>;

  /**
   * Set the authenticated state after a successful login or refresh.
   *
   * @param user         The authenticated user profile.
   * @param accessToken  The new JWT access token.
   * @param refreshToken The new refresh token to store in sessionStorage.
   */
  setAuth: (user: User, accessToken: string, refreshToken: string) => void;

  /**
   * Clear all authentication state and stored tokens.
   * Called after logout or token refresh failure.
   */
  clearAuth: () => void;
}

/**
 * Module-level singleton Promise that tracks an in-flight initialize() call.
 * This ensures concurrent callers (e.g. page.tsx + protected layout) await
 * the same single network request instead of firing duplicate refreshes.
 */
let _initializePromise: Promise<void> | null = null;

/** Set to true once initialize() has completed (success or failure). */
let _initialized = false;

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isAuthenticated: false,
  isInitializing: true,

  initialize: async () => {
    // If already completed, this is a no-op.
    if (_initialized) return;

    // If in-flight, reuse the existing Promise — do not issue a second request.
    if (_initializePromise) {
      return _initializePromise;
    }

    if (typeof window === "undefined") {
      _initialized = true;
      set({ isInitializing: false });
      return;
    }

    _initializePromise = (async () => {
      const storedRefreshToken = sessionStorage.getItem(
        "intelliflow_refresh_token",
      );

      if (!storedRefreshToken) {
        set({ isInitializing: false });
        return;
      }

      try {
        const response = await authService.refreshToken(storedRefreshToken);
        const { access_token, refresh_token, user } = response.data;
        get().setAuth(user, access_token, refresh_token);
      } catch {
        // Refresh token expired or invalid — treat as unauthenticated (expected).
        // Do NOT log an error here; a missing/expired token is a normal state.
        get().clearAuth();
      } finally {
        _initialized = true;
        set({ isInitializing: false });
      }
    })();

    return _initializePromise;
  },

  setAuth: (user: User, accessToken: string, refreshToken: string) => {
    // Store access token in memory (not localStorage — avoids XSS persistence)
    if (typeof window !== "undefined") {
      window.__intelliflow_access_token = accessToken;
      sessionStorage.setItem("intelliflow_refresh_token", refreshToken);
    }
    set({ user, isAuthenticated: true });
  },

  clearAuth: () => {
    if (typeof window !== "undefined") {
      window.__intelliflow_access_token = undefined;
      sessionStorage.removeItem("intelliflow_refresh_token");
    }
    // Reset the idempotency guards so the next login/logout cycle can
    // re-initialize correctly (e.g. after logging out and back in).
    _initializePromise = null;
    _initialized = false;
    set({ user: null, isAuthenticated: false });
  },
}));
