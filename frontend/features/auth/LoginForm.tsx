"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useAuth } from "@/hooks/useAuth";

const loginSchema = z.object({
  email: z.string().min(1, "Email is required").email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
});

type LoginFormData = z.infer<typeof loginSchema>;

export function LoginForm() {
  const router = useRouter();
  const { login } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = async (data: LoginFormData) => {
    setServerError(null);
    setIsLoading(true);
    try {
      await login(data);
      router.push("/dashboard");
    } catch (err: unknown) {
      if (
        err &&
        typeof err === "object" &&
        "response" in err &&
        err.response &&
        typeof err.response === "object" &&
        "data" in err.response &&
        err.response.data &&
        typeof err.response.data === "object" &&
        "detail" in err.response.data
      ) {
        setServerError(String((err.response as { data: { detail: unknown } }).data.detail));
      } else {
        setServerError("Invalid email or password. Please try again.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={{ width: "100%", maxWidth: 380 }}>
      {/* Heading */}
      <div style={{ marginBottom: 36 }}>
        <p className="eyebrow" style={{ color: "var(--ink-40)", marginBottom: 12 }}>
          Welcome back
        </p>
        <h2
          style={{
            fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
            fontSize: 28,
            fontWeight: 800,
            letterSpacing: "-0.03em",
            color: "#f1f5f9",
            lineHeight: 1.15,
            margin: 0,
          }}
        >
          Sign in to
          <br />
          IntelliFlow
        </h2>
      </div>

      {/* Error */}
      {serverError && (
        <div
          style={{
            marginBottom: 20,
            padding: "12px 14px",
            background: "rgb(220 38 38 / 0.08)",
            border: "1px solid rgb(220 38 38 / 0.3)",
            borderRadius: 8,
            fontSize: 13,
            color: "#f87171",
            display: "flex",
            gap: 8,
            alignItems: "flex-start",
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 1 }}>
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {serverError}
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {/* Email */}
        <div>
          <label className="input-label" htmlFor="email-input">
            Email address
          </label>
          <input
            {...register("email")}
            id="email-input"
            type="email"
            autoComplete="email"
            placeholder="name@company.com"
            className="input"
          />
          {errors.email && (
            <p style={{ marginTop: 4, fontSize: 12, color: "#f87171" }}>
              {errors.email.message}
            </p>
          )}
        </div>

        {/* Password */}
        <div>
          <label className="input-label" htmlFor="password-input">
            Password
          </label>
          <input
            {...register("password")}
            id="password-input"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            className="input"
          />
          {errors.password && (
            <p style={{ marginTop: 4, fontSize: 12, color: "#f87171" }}>
              {errors.password.message}
            </p>
          )}
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={isLoading}
          className="btn btn-primary"
          style={{ width: "100%", marginTop: 4, padding: "12px 20px", justifyContent: "center" }}
        >
          {isLoading ? (
            <>
              <span
                style={{
                  width: 14,
                  height: 14,
                  border: "2px solid rgb(255 255 255 / 0.3)",
                  borderTopColor: "white",
                  borderRadius: "50%",
                  animation: "spin 0.7s linear infinite",
                  display: "inline-block",
                }}
              />
              Signing in...
            </>
          ) : (
            "Sign in →"
          )}
        </button>
      </form>

      <p
        style={{
          marginTop: 24,
          textAlign: "center",
          fontSize: 13,
          color: "var(--ink-40)",
        }}
      >
        No account?{" "}
        <Link
          href="/register"
          style={{ color: "var(--accent)", fontWeight: 600, textDecoration: "none" }}
        >
          Register here
        </Link>
      </p>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
