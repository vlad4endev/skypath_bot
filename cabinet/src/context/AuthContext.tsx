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

interface AuthUser {
  full_name: string | null;
  email: string | null;
}

interface AuthState {
  loading: boolean;
  authenticated: boolean;
  brand: string;
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: {
    email: string;
    password: string;
    password_confirm?: string;
    first_name?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [brand, setBrand] = useState('SkyPath VPN');
  const [user, setUser] = useState<AuthUser | null>(null);

  const checkSession = useCallback(async () => {
    if (!getToken()) {
      setAuthenticated(false);
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      setBrand(me.brand || 'SkyPath VPN');
      setUser(me.user);
      setAuthenticated(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) clearToken();
      setAuthenticated(false);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    setToken(res.token);
    const me = await api.me();
    setBrand(me.brand || 'SkyPath VPN');
    setUser(me.user);
    setAuthenticated(true);
  }, []);

  const register = useCallback(async (payload: {
    email: string;
    password: string;
    password_confirm?: string;
    first_name?: string;
  }) => {
    const res = await api.register(payload);
    setToken(res.token);
    const me = await api.me();
    setBrand(me.brand || 'SkyPath VPN');
    setUser(me.user);
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
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ loading, authenticated, brand, user, login, register, logout }),
    [loading, authenticated, brand, user, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}
