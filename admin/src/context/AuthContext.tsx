import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { api, clearToken, getToken, setToken, ApiError } from '../api/client';

interface AuthState {
  loading: boolean;
  authenticated: boolean;
  brand: string;
  login: (password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [brand, setBrand] = useState('SkyPath VPN');

  const checkSession = useCallback(async () => {
    if (!getToken()) {
      setAuthenticated(false);
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      setBrand(me.brand || 'SkyPath VPN');
      setAuthenticated(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) clearToken();
      setAuthenticated(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  const login = useCallback(async (password: string) => {
    const res = await api.login(password);
    setToken(res.token);
    const me = await api.me();
    setBrand(me.brand || 'SkyPath VPN');
    setAuthenticated(true);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* ignore */
    }
    clearToken();
    setAuthenticated(false);
  }, []);

  const value = useMemo(
    () => ({ loading, authenticated, brand, login, logout }),
    [loading, authenticated, brand, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}
