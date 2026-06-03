"use client";
import { createContext, useContext, useState, useEffect } from "react";
import { DARK, LIGHT } from "@/lib/theme";

const ThemeContext = createContext({ C: DARK, isDark: true, toggleTheme: () => {} });

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(true);

  // Restore from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem("spirulina-theme");
      if (saved === "light") setIsDark(false);
    } catch {}
  }, []);

  // Apply class to <html> and persist
  useEffect(() => {
    try {
      document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");
      localStorage.setItem("spirulina-theme", isDark ? "dark" : "light");
    } catch {}
  }, [isDark]);

  const toggleTheme = () => setIsDark((d) => !d);

  return (
    <ThemeContext.Provider value={{ C: isDark ? DARK : LIGHT, isDark, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
