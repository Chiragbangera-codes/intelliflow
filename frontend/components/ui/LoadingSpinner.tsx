"use client";

import React from "react";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  message?: string;
  className?: string;
}

const sizeMap = {
  sm: "w-5 h-5 border-2",
  md: "w-8 h-8 border-3",
  lg: "w-12 h-12 border-4",
};

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = "md",
  message,
  className = "",
}) => {
  return (
    <div className={`flex flex-col items-center justify-center space-y-3 py-6 ${className}`}>
      <div
        className={`${sizeMap[size]} border-blue-600 border-t-transparent rounded-full animate-spin`}
      />
      {message && (
        <p className="text-sm font-medium text-gray-500 dark:text-gray-400 animate-pulse">
          {message}
        </p>
      )}
    </div>
  );
};
