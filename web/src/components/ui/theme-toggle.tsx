"use client";

import { Moon, Sun, Monitor } from "lucide-react";
import { useTheme } from "@/lib/theme-context";

interface ThemeToggleProps {
  className?: string;
}

export function ThemeToggle({ className = "" }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme();

  const cycleTheme = () => {
    if (theme === "light") setTheme("dark");
    else if (theme === "dark") setTheme("system");
    else setTheme("light");
  };

  return (
    <button
      onClick={cycleTheme}
      className={`p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${className}`}
      title={`Current: ${theme}. Click to cycle.`}
    >
      {theme === "light" && <Sun className="h-5 w-5 text-amber-500" />}
      {theme === "dark" && <Moon className="h-5 w-5 text-violet-400" />}
      {theme === "system" && <Monitor className="h-5 w-5 text-gray-500 dark:text-gray-400" />}
    </button>
  );
}

export function ThemeSelector({ className = "" }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme();

  return (
    <div className={`flex items-center gap-1 p-1 bg-gray-100 dark:bg-gray-800 rounded-lg ${className}`}>
      <button
        onClick={() => setTheme("light")}
        className={`p-2 rounded-md transition-colors ${
          theme === "light"
            ? "bg-white dark:bg-gray-700 shadow-sm"
            : "hover:bg-gray-200 dark:hover:bg-gray-700"
        }`}
        title="Light mode"
      >
        <Sun className={`h-4 w-4 ${theme === "light" ? "text-amber-500" : "text-gray-500"}`} />
      </button>
      <button
        onClick={() => setTheme("dark")}
        className={`p-2 rounded-md transition-colors ${
          theme === "dark"
            ? "bg-white dark:bg-gray-700 shadow-sm"
            : "hover:bg-gray-200 dark:hover:bg-gray-700"
        }`}
        title="Dark mode"
      >
        <Moon className={`h-4 w-4 ${theme === "dark" ? "text-violet-400" : "text-gray-500"}`} />
      </button>
      <button
        onClick={() => setTheme("system")}
        className={`p-2 rounded-md transition-colors ${
          theme === "system"
            ? "bg-white dark:bg-gray-700 shadow-sm"
            : "hover:bg-gray-200 dark:hover:bg-gray-700"
        }`}
        title="System preference"
      >
        <Monitor className={`h-4 w-4 ${theme === "system" ? "text-cyan-500" : "text-gray-500"}`} />
      </button>
    </div>
  );
}
