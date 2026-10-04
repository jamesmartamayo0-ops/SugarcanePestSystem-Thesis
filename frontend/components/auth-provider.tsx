"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { getCurrentUser, type AuthSession, type AuthUser } from "@/lib/auth";
import { advanceAuthSessionVersion, getAuthSessionVersion, onSessionExpired } from "@/lib/api";

type AuthState =
  | { status: "loading"; user: null; csrfToken: null }
  | { status: "unauthenticated"; user: null; csrfToken: null }
  | { status: "error"; user: null; csrfToken: null }
  | { status: "authenticated"; user: AuthUser; csrfToken: string };

type AuthContextValue = AuthState & {
  setSession: (session: AuthSession | null) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    status: "loading",
    user: null,
    csrfToken: null,
  });

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const requestVersion = getAuthSessionVersion();
    const unsubscribe = onSessionExpired(() => {
      setState({ status: "unauthenticated", user: null, csrfToken: null });
    });

    getCurrentUser(controller.signal)
      .then((session) => {
        if (active && requestVersion === getAuthSessionVersion()) {
          setState(
            session
              ? { status: "authenticated", user: session.user, csrfToken: session.csrfToken }
              : { status: "unauthenticated", user: null, csrfToken: null },
          );
        }
      })
      .catch(() => {
        if (active && requestVersion === getAuthSessionVersion()) {
          setState({ status: "error", user: null, csrfToken: null });
        }
      });

    return () => {
      active = false;
      controller.abort();
      unsubscribe();
    };
  }, []);

  function setSession(session: AuthSession | null) {
    advanceAuthSessionVersion();
    setState(
      session
        ? { status: "authenticated", user: session.user, csrfToken: session.csrfToken }
        : { status: "unauthenticated", user: null, csrfToken: null },
    );
  }

  return (
    <AuthContext.Provider value={{ ...state, setSession }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("AuthProvider is required.");
  }
  return context;
}
