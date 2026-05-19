import { useAuth } from "@/store/useAuth";
import { useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";

export function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isAuthenticated) {
      navigate({ to: "/login" });
    }
  }, [isAuthenticated, navigate]);

  if (!isAuthenticated) return null;

  return children;
}
