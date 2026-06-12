import { useEffect, useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import { Mail, Lock, ArrowRight } from 'lucide-react';
import { ApiError, api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { Logo, Spinner } from '../components/ui';

export function LoginPage() {
  const { authenticated, loading, login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [brand, setBrand] = useState('SkyPath VPN');
  const [supportUrl, setSupportUrl] = useState('');
  const [botUsername, setBotUsername] = useState('');

  useEffect(() => {
    api.config().then((cfg) => {
      setBrand(cfg.brand_name);
      setSupportUrl(cfg.support_url);
      setBotUsername(cfg.bot_username);
    }).catch(() => {});
  }, []);

  if (loading) {
    return (
      <div className="boot-screen">
        <Spinner size={32} />
      </div>
    );
  }

  if (authenticated) return <Navigate to="/" replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка входа');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-bg" aria-hidden />
      <div className="login-grid">
        <section className="login-hero">
          <Logo brand={brand} size={56} />
          <h1>Личный кабинет</h1>
          <p>
            Управляйте подпиской, ключами и тарифами из браузера.
            Войдите с email и паролем, которые вы задали в Telegram Mini App.
          </p>
          <ul className="login-features">
            <li>Статус подписки и трафик в реальном времени</li>
            <li>VPN-ключи и быстрое подключение</li>
            <li>Оплата и продление тарифов</li>
          </ul>
        </section>

        <div className="login-card">
          <h2>Вход</h2>
          <p className="login-hint">Используйте данные из регистрации в боте</p>

          <form onSubmit={onSubmit} className="login-form">
            <label className="field">
              <span>Email</span>
              <div className="input-wrap">
                <Mail size={18} className="input-icon" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  autoFocus
                  required
                />
              </div>
            </label>

            <label className="field">
              <span>Пароль</span>
              <div className="input-wrap">
                <Lock size={18} className="input-icon" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Минимум 8 символов"
                  autoComplete="current-password"
                  required
                />
              </div>
            </label>

            {error && <p className="form-error">{error}</p>}

            <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
              {submitting ? 'Вход…' : (
                <>
                  Войти
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </form>

          <div className="login-footer">
            <p>Ещё нет аккаунта?</p>
            <p className="muted">
              Откройте Mini App в{' '}
              {botUsername ? (
                <a href={`https://t.me/${botUsername}`} target="_blank" rel="noreferrer">
                  @{botUsername}
                </a>
              ) : (
                'Telegram-боте'
              )}{' '}
              и пройдите регистрацию email + пароль.
            </p>
            {supportUrl && (
              <a href={supportUrl} target="_blank" rel="noreferrer" className="support-link">
                Нужна помощь?
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
