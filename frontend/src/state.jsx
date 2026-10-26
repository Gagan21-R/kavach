import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { get, onStepUp, onUnauthorized, post, setCsrf } from "./api";

const AuthCtx = createContext(null);
const AgentCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [frozen, setFrozen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [stepUp, setStepUp] = useState(null); // { resolve }
  const resolver = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const s = await get("/auth/session", { allowError: true });
      if (s.status === 200) {
        setCsrf(s.data.csrf_token);
        setUser(s.data.user);
        setFrozen(s.data.frozen);
      } else {
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    onUnauthorized(() => setUser(null));
    onStepUp(() => new Promise((resolve) => {
      resolver.current = resolve;
      setStepUp({});
    }));
  }, [refresh]);

  const login = async (email, password) => {
    const r = await post("/auth/login", { email, password });
    setCsrf(r.csrf_token);
    setUser(r.user);
    await refresh();
  };
  const register = async (email, password) => {
    await post("/auth/register", { email, password });
    await login(email, password);
  };
  const logout = async () => {
    try { await post("/auth/logout"); } catch { /* already signed out */ }
    setCsrf(null);
    setUser(null);
  };
  const finishStepUp = (ok) => {
    resolver.current?.(ok);
    resolver.current = null;
    setStepUp(null);
  };

  return (
    <AuthCtx.Provider value={{ user, frozen, setFrozen, loading, login, register, logout, refresh, stepUp, finishStepUp }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);

// The demo agent's API key lives only in memory: it is shown once by the server and never stored in the browser.
export function AgentProvider({ children }) {
  const [agent, setAgent] = useState(null); // { id, name, key }
  return <AgentCtx.Provider value={{ agent, setAgent }}>{children}</AgentCtx.Provider>;
}

export const useAgent = () => useContext(AgentCtx);

export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fn());
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}
