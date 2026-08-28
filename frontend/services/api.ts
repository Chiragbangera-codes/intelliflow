/**
 * Axios HTTP client instance.
 *
 * Configures a shared Axios instance for all API calls:
 *   - Base URL from environment variable
 *   - Default JSON content type
 *   - Request interceptor: attaches the access token from the auth store
 *   - Response interceptor: handles 401 (token refresh or redirect to login)
 *
 * Token storage strategy (Milestone 2):
 *   - Access token: in-memory (Zustand store) — lost on page reload
 *   - Refresh token: sessionStorage — survives navigation, not browser close
 *
 * Production note: Move refresh token to HttpOnly Secure SameSite=Strict
 * cookie once the backend cookie endpoint is implemented (avoids XSS risk).
 */

import axios, { type AxiosInstance, type AxiosResponse } from "axios";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// ---------------------------------------------------------------------------
// Create the Axios instance
// ---------------------------------------------------------------------------
export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 180_000, // 180 seconds default for RAG and LLM operations
});

// ---------------------------------------------------------------------------
// Request interceptor — attach access token if present
// ---------------------------------------------------------------------------
apiClient.interceptors.request.use(
  (config) => {
    if (typeof window !== "undefined") {
      const accessToken = window.__intelliflow_access_token;
      if (accessToken && config.headers) {
        if (typeof config.headers.set === "function") {
          config.headers.set("Authorization", `Bearer ${accessToken}`);
        } else {
          config.headers["Authorization"] = `Bearer ${accessToken}`;
        }
      }
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// ---------------------------------------------------------------------------
// Response interceptor — handle 401 with single-flight token refresh
// ---------------------------------------------------------------------------

/**
 * Shared in-flight refresh promise.
 * Ensures concurrent 401s reuse the same token rotation call.
 */
let _refreshPromise: Promise<string> | null = null;

apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error) => {
    const originalRequest = error.config;
    if (!originalRequest) {
      return Promise.reject(error);
    }

    const requestUrl: string = originalRequest.url ?? "";
    const isAuthEndpoint =
      requestUrl.includes("/auth/refresh") ||
      requestUrl.includes("/auth/login");

    // Attempt single-flight refresh on 401 (skip auth endpoints and already retried requests).
    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !isAuthEndpoint &&
      typeof window !== "undefined"
    ) {
      originalRequest._retry = true;

      // Start or reuse in-flight refresh promise
      if (!_refreshPromise) {
        _refreshPromise = (async () => {
          const refreshToken = sessionStorage.getItem(
            "intelliflow_refresh_token",
          );
          if (!refreshToken) {
            throw new Error("No refresh token available");
          }

          // Use raw standalone axios to avoid interceptor recursion
          const refreshResp = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          });

          const {
            access_token,
            refresh_token: newRefreshToken,
            user,
          } = refreshResp.data.data;

          // Update memory and storage
          window.__intelliflow_access_token = access_token;
          sessionStorage.setItem("intelliflow_refresh_token", newRefreshToken);

          // Synchronize Zustand store if available
          try {
            const { useAuthStore } = await import("@/store/auth.store");
            if (user) {
              useAuthStore
                .getState()
                .setAuth(user, access_token, newRefreshToken);
            }
          } catch {
            // Non-critical fallback
          }

          return access_token;
        })()
          .catch(async (refreshError) => {
            // Clear all auth state
            window.__intelliflow_access_token = undefined;
            sessionStorage.removeItem("intelliflow_refresh_token");

            try {
              const { useAuthStore } = await import("@/store/auth.store");
              useAuthStore.getState().clearAuth();
            } catch {
              // Non-critical fallback
            }

            // Redirect to login if not already there
            if (
              typeof window !== "undefined" &&
              !window.location.pathname.includes("/login")
            ) {
              // eslint-disable-next-line @next/next/no-location-assign-relative-destination
              window.location.href = "/login";
            }

            throw refreshError;
          })
          .finally(() => {
            _refreshPromise = null;
          });
      }

      try {
        const newAccessToken = await _refreshPromise;

        // Apply new token to the retry request
        if (originalRequest.headers) {
          if (typeof originalRequest.headers.set === "function") {
            originalRequest.headers.set(
              "Authorization",
              `Bearer ${newAccessToken}`,
            );
          } else {
            originalRequest.headers["Authorization"] = `Bearer ${newAccessToken}`;
          }
        }

        return apiClient(originalRequest);
      } catch {
        return Promise.reject(error);
      }
    }

    return Promise.reject(error);
  },
);

// ---------------------------------------------------------------------------
// Type augmentation for the window object
// ---------------------------------------------------------------------------
declare global {
  interface Window {
    __intelliflow_access_token?: string;
  }
}

export default apiClient;

