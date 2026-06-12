import { useState, type FormEvent } from 'react';
import { Shield } from 'lucide-react';
import { ApiError } from '../api/client';
import { Logo } from '../components/ui';
import { useAuth } from '../context/AuthContext';

export function LoginPage() {
  const { login } = useAuth();
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка входа');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-bg" aria-hidden />
      <div className="login-card">
        <div className="login-header">
          <Logo size={52} brand="SkyPath" />
          <p className="login-subtitle">Панель управления VPN-сервисом</p>
        </div>
        <form onSubmit={onSubmit} className="login-form">
          <label className="field">
            <span>Пароль администратора</span>
            <div className="input-wrap">
              <Shield size={18} className="input-icon" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Введите пароль"
                autoComplete="current-password"
                autoFocus
                required
              />
            </div>
          </label>
          {error && <p className="form-error">{error}</p>}
          <button type="submit" className="btn btn--primary btn--block" disabled={loading}>
            {loading ? 'Вход…' : 'Войти'}
          </button>
        </form>
      </div>
    </div>
  );
}
