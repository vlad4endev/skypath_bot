import { useEffect, useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { ArrowRight, Lock, Mail, User } from 'lucide-react';
import { ApiError } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useI18n } from '../i18n/I18nContext';
import { LoginPromo } from '../components/LoginPromo';
import { Spinner } from '../components/ui';
import { api } from '../api/client';

export function RegisterPage() {
  const { authenticated, loading, register } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [brand, setBrand] = useState('SkyPath VPN');

  useEffect(() => {
    api.config().then((cfg) => setBrand(cfg.brand_name)).catch(() => {});
  }, []);

  if (loading) {
    return (
      <div className="boot-screen">
        <Spinner size={32} />
      </div>
    );
  }

  if (authenticated) return <Navigate to="/app" replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== passwordConfirm) {
      setError('Пароли не совпадают');
      return;
    }

    setSubmitting(true);
    try {
      await register({
        email: email.trim(),
        password,
        password_confirm: passwordConfirm,
        first_name: name.trim() || undefined,
      });
      navigate('/app/plans', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка регистрации');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-bg" aria-hidden />
      <div className="login-grid">
        <LoginPromo brand={brand} />

        <div className="login-card">
          <h2>{t('register_title')}</h2>
          <p className="login-hint">{t('register_subtitle')}</p>

          <form onSubmit={onSubmit} className="login-form">
            <label className="field">
              <span>{t('register_name')}</span>
              <div className="input-wrap">
                <User size={18} className="input-icon" />
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Как к вам обращаться"
                  autoComplete="name"
                  autoFocus
                />
              </div>
            </label>

            <label className="field">
              <span>{t('email')}</span>
              <div className="input-wrap">
                <Mail size={18} className="input-icon" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                />
              </div>
            </label>

            <label className="field">
              <span>{t('password')}</span>
              <div className="input-wrap">
                <Lock size={18} className="input-icon" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Минимум 8 символов"
                  autoComplete="new-password"
                  required
                  minLength={8}
                />
              </div>
            </label>

            <label className="field">
              <span>{t('register_password_confirm')}</span>
              <div className="input-wrap">
                <Lock size={18} className="input-icon" />
                <input
                  type="password"
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  placeholder="Ещё раз"
                  autoComplete="new-password"
                  required
                  minLength={8}
                />
              </div>
            </label>

            {error && <p className="form-error">{error}</p>}

            <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
              {submitting ? '…' : (
                <>
                  {t('register_btn')}
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </form>

          <div className="login-footer">
            <p>{t('register_have_account')}</p>
            <Link to="/login" className="btn btn--ghost btn--block">
              {t('login_btn')}
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
