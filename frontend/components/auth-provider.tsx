"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { getCurrentUser, type AuthSession, type AuthUser } from "@/lib/auth";

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

    getCurrentUser(controller.signal)
      .then((session) => {
        if (active) {
          setState(
            session
              ? { status: "authenticated", user: session.user, csrfToken: session.csrfToken }
              : { status: "unauthenticated", user: null, csrfToken: null },
          );
        }
      })
      .catch(() => {
        if (active) {
          setState({ status: "error", user: null, csrfToken: null });
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  function setSession(session: AuthSession | null) {
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
