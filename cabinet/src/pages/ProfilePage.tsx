import { useCallback, useEffect, useState } from 'react';
import { Calendar, LogOut, Mail, RefreshCw, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { DashboardData } from '../types';
import { formatDate } from '../utils/format';
import { Spinner, StatusBadge } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { useI18n } from '../i18n/I18nContext';

export function ProfilePage() {
  const { user: authUser, logout } = useAuth();
  const { t, locale } = useI18n();
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      setData(await api.dashboard());
    } catch (e) {
      setError(e instanceof Error ? e.message : t('load_error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="page-loading">
        <Spinner size={32} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="page-error">
        <p>{error || t('load_error')}</p>
        <button type="button" className="btn btn--primary" onClick={load}>
          <RefreshCw size={18} />
          {t('retry')}
        </button>
      </div>
    );
  }

  const sub = data.subscription;
  const user = data.user;

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="page profile-page">
      <header className="page-header">
        <h1>{t('nav_profile')}</h1>
        <p className="subtitle">Данные аккаунта и подписки</p>
      </header>

      <section className="profile-hero">
        <div className="profile-avatar-xl">
          {(user?.full_name || authUser?.full_name || '?')[0]?.toUpperCase()}
        </div>
        <div>
          <h2>{user?.full_name || authUser?.full_name || t('user')}</h2>
          <p className="muted">{user?.email || authUser?.email}</p>
        </div>
      </section>

      <section className="profile-details">
        <div className="detail-row">
          <Mail size={18} />
          <span>Email</span>
          <strong>{user?.email || '—'}</strong>
        </div>
        <div className="detail-row">
          <User size={18} />
          <span>Имя</span>
          <strong>{user?.full_name || '—'}</strong>
        </div>
        <div className="detail-row">
          <Calendar size={18} />
          <span>{t('client_since')}</span>
          <strong>{formatDate(user?.member_since, locale)}</strong>
        </div>
        <div className="detail-row">
          <span>{t('referrals')}</span>
          <strong>{user?.referrals_count ?? 0}</strong>
        </div>
      </section>

      {sub && (
        <section className="card">
          <div className="card-head">
            <h2>Подписка</h2>
            <StatusBadge active={sub.is_active} />
          </div>
          <div className="profile-sub-grid">
            <div>
              <span className="muted">Тариф</span>
              <strong>{sub.plan_name}</strong>
            </div>
            <div>
              <span className="muted">До</span>
              <strong>{formatDate(sub.expires_at, locale)}</strong>
            </div>
            <div>
              <span className="muted">Устройств</span>
              <strong>{sub.limit_ip}</strong>
            </div>
            <div>
              <span className="muted">Осталось</span>
              <strong>{sub.days_left} дн.</strong>
            </div>
          </div>
        </section>
      )}

      <div className="profile-actions">
        <button type="button" className="btn btn--ghost btn--block" onClick={handleLogout}>
          <LogOut size={18} aria-hidden />
          {t('logout')}
        </button>
      </div>
    </div>
  );
}
