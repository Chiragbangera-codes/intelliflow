/**
 * Zustand global state store.
 *
 * Per SYSTEM_ARCHITECTURE §5, Zustand manages client-side global state:
 *   - Current authenticated user
 *   - Theme preference (light/dark)
 *   - Notification state
 *   - Language / locale
 *
 * Server state (API data) is managed by React Query — not Zustand.
 * Zustand is only for UI state and session data.
 *
 * Stores:
 *   store/
 *     auth.store.ts          ← User session
 *     notification.store.ts  ← Notification list + unread count + polling
 *     theme.store.ts         ← Theme preference (future)
 */

export { useAuthStore } from "./auth.store";
export { useNotificationStore } from "./notification.store";

