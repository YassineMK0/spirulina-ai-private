"use client";
import { createContext, useContext, useState, useEffect } from "react";
import { authMe } from "@/lib/api";

const AuthContext = createContext({
  user:    null,
  loading: true,
  login:   () => {},
  logout:  () => {},
});

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null);
  const [loading, setLoading] = useState(true);

  // On mount: restore session from localStorage
  useEffect(() => {
    const token = localStorage.getItem("spirulina-token");
    if (!token) { setLoading(false); return; }
    authMe(token)
      .then((u) => { if (u) setUser(u); else localStorage.removeItem("spirulina-token"); })
      .catch(() => localStorage.removeItem("spirulina-token"))
      .finally(() => setLoading(false));
  }, []);

  const login = ({ token, user: u }) => {
    localStorage.setItem("spirulina-token", token);
    setUser(u);
  };

  const logout = () => {
    localStorage.removeItem("spirulina-token");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
