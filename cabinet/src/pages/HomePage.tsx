import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, Gift, RefreshCw, Shield, Zap } from 'lucide-react';
import { api } from '../api/client';
import type { DashboardData } from '../types';
import { formatDate, getInitials } from '../utils/format';
import { Spinner, StatusBadge, TrafficRing } from '../components/ui';

export function HomePage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const dash = await api.dashboard();
      setData(dash);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="page-loading">
        <Spinner size={32} />
        <span>Загрузка кабинета…</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="page-error">
        <p>{error || 'Не удалось загрузить данные'}</p>
        <button type="button" className="btn btn--primary" onClick={load}>
          <RefreshCw size={18} />
          Повторить
        </button>
      </div>
    );
  }

  const sub = data.subscription;
  const user = data.user;
  const traffic = sub?.traffic;
  const usedBytes = (traffic?.up ?? 0) + (traffic?.down ?? 0);
  const limitBytes = sub?.traffic_gb ? sub.traffic_gb * 1024 ** 3 : traffic?.limit ?? 0;

  return (
    <div className="page home-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Добро пожаловать</p>
          <h1>{user?.full_name || 'Пользователь'}</h1>
          {user?.email && <p className="subtitle">{user.email}</p>}
        </div>
        <div className="profile-avatar lg">{getInitials(user?.full_name)}</div>
      </header>

      <div className="stats-row">
        <div className="stat-card">
          <Calendar size={20} />
          <div>
            <span>Клиент с</span>
            <strong>{formatDate(user?.member_since)}</strong>
          </div>
        </div>
        <div className="stat-card">
          <Gift size={20} />
          <div>
            <span>Рефералы</span>
            <strong>{user?.referrals_count ?? 0}</strong>
          </div>
        </div>
      </div>

      {sub && data.has_subscription ? (
        <section className="card subscription-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Текущий тариф</p>
              <h2>{sub.plan_name}</h2>
            </div>
            <StatusBadge active={sub.is_active} />
          </div>

          <div className="sub-grid">
            <div className="sub-details">
              <div className="detail-row">
                <Shield size={18} />
                <span>Устройств</span>
                <strong>{sub.limit_ip}</strong>
              </div>
              <div className="detail-row">
                <Zap size={18} />
                <span>Осталось дней</span>
                <strong className={sub.days_left <= 3 ? 'text-warning' : ''}>
                  {sub.days_left}
                </strong>
              </div>
              <div className="detail-row">
                <Calendar size={18} />
                <span>До</span>
                <strong>{formatDate(sub.expires_at)}</strong>
              </div>
            </div>

            {limitBytes > 0 && (
              <TrafficRing used={usedBytes} limit={limitBytes} size={130} />
            )}
          </div>

          <div className="card-actions">
            <Link to="/keys" className="btn btn--primary">
              Подключить VPN
            </Link>
            {sub.days_left <= 7 && (
              <Link to="/plans" className="btn btn--secondary">
                Продлить
              </Link>
            )}
          </div>
        </section>
      ) : (
        <section className="card empty-card">
          <div className="empty-icon">🛡️</div>
          <h2>Нет активной подписки</h2>
          <p>Выберите тариф и получите доступ к VPN за пару минут.</p>
          <Link to="/plans" className="btn btn--primary">
            Выбрать тариф
          </Link>
        </section>
      )}

      <section className="card quick-links">
        <h3>Быстрые действия</h3>
        <div className="quick-grid">
          <Link to="/keys" className="quick-item">
            <KeyRoundIcon />
            <span>Мои ключи</span>
          </Link>
          <Link to="/plans" className="quick-item">
            <CreditIcon />
            <span>Тарифы</span>
          </Link>
          <Link to="/support" className="quick-item">
            <HelpIcon />
            <span>Настройка</span>
          </Link>
        </div>
      </section>
    </div>
  );
}

function KeyRoundIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4" />
    </svg>
  );
}

function CreditIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="1" y="4" width="22" height="16" rx="2" />
      <path d="M1 10h22" />
    </svg>
  );
}

function HelpIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
      <path d="M12 17h.01" />
    </svg>
  );
}
