/**
 * Authentication service.
 *
 * All auth-related API calls go through this service.
 * Components and hooks never call the API directly.
 *
 * Pattern: Component → Hook/Store → Service → apiClient → Backend
 */

import apiClient from "./api";
import type {
  ApiResponse,
  AuthTokens,
  LoginRequest,
  LogoutRequest,
  RegisterRequest,
  User,
} from "@/types";

// ---------------------------------------------------------------------------
// Register
// ---------------------------------------------------------------------------

/**
 * Register a new user account.
 * Returns the created user's safe profile on success.
 */
export async function register(
  data: RegisterRequest,
): Promise<ApiResponse<User>> {
  const response = await apiClient.post<ApiResponse<User>>(
    "/auth/register",
    data,
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------

/**
 * Authenticate with email and password.
 * Returns access token, refresh token, and user profile.
 * Caller is responsible for storing the tokens securely.
 */
export async function login(
  data: LoginRequest,
): Promise<ApiResponse<AuthTokens>> {
  const response = await apiClient.post<ApiResponse<AuthTokens>>(
    "/auth/login",
    data,
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Token refresh
// ---------------------------------------------------------------------------

/**
 * Refresh the access token using a valid refresh token.
 * Returns a new token pair (rotation — old token is invalidated).
 */
export async function refreshToken(
  refreshToken: string,
): Promise<ApiResponse<AuthTokens>> {
  const response = await apiClient.post<ApiResponse<AuthTokens>>(
    "/auth/refresh",
    { refresh_token: refreshToken },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Logout
// ---------------------------------------------------------------------------

/**
 * Revoke the refresh token server-side.
 * Must be called with a valid access token in the Authorization header.
 */
export async function logout(data: LogoutRequest): Promise<void> {
  await apiClient.post("/auth/logout", data);
}

// ---------------------------------------------------------------------------
// Current user
// ---------------------------------------------------------------------------

/**
 * Fetch the currently authenticated user's profile.
 * Requires a valid access token.
 */
export async function getCurrentUser(): Promise<ApiResponse<User>> {
  const response = await apiClient.get<ApiResponse<User>>("/auth/me");
  return response.data;
}
