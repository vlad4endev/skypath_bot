import { useCallback, useEffect, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Users,
  Wallet,
  Zap,
  Clock,
  AlertTriangle,
  Ban,
  Server,
  RefreshCw,
  TrendingUp,
  UserMinus,
  Repeat,
  Activity,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  ClientAnalytics,
  DashboardStats,
  InactivePayerRow,
  PlanStat,
  RevenuePoint,
  UserRow,
  UsersGrowthPoint,
  XuiStatusResponse,
} from '../types';
import { fmtBytes, fmtDate, fmtDaysLeft, fmtMoney, fmtPct, fmtUptime, daysLeftClass } from '../utils/format';
import { Badge, Spinner, StatCard } from '../components/ui';
import { UserCardModal } from '../modals/UserCardModal';

const PLAN_COLORS = ['#6366f1', '#38bdf8', '#34d399', '#fbbf24', '#f472b6'];
const INACTIVE_DAYS_OPTIONS = [30, 60, 90];

function usagePct(current?: number, total?: number): number {
  if (!current || !total) return 0;
  return Math.min(100, Math.round((current / total) * 100));
}

function MetricBar({ label, pct, hint }: { label: string; pct: number; hint?: string }) {
  const tone = pct >= 90 ? 'danger' : pct >= 75 ? 'warning' : 'normal';
  return (
    <div className="metric-bar">
      <div className="metric-bar__head">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <div className="metric-bar__track">
        <div className={`metric-bar__fill metric-bar__fill--${tone}`} style={{ width: `${pct}%` }} />
      </div>
      {hint && <div className="metric-bar__hint">{hint}</div>}
    </div>
  );
}

function XrayBadge({ state }: { state?: string }) {
  const normalized = (state ?? 'unknown').toLowerCase();
  if (normalized === 'running') return <Badge variant="success">Xray: работает</Badge>;
  if (normalized === 'stop' || normalized === 'stopped') return <Badge variant="warning">Xray: остановлен</Badge>;
  if (normalized === 'error') return <Badge variant="danger">Xray: ошибка</Badge>;
  return <Badge variant="muted">Xray: {state ?? '—'}</Badge>;
}

interface DashboardPageProps {
  onXuiSync: (userId: number) => void;
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

export function DashboardPage({ onXuiSync, onToast }: DashboardPageProps) {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [analytics, setAnalytics] = useState<ClientAnalytics | null>(null);
  const [revenue, setRevenue] = useState<RevenuePoint[]>([]);
  const [growth, setGrowth] = useState<UsersGrowthPoint[]>([]);
  const [plans, setPlans] = useState<PlanStat[]>([]);
  const [xui, setXui] = useState<XuiStatusResponse | null>(null);
  const [xuiError, setXuiError] = useState<string | null>(null);
  const [xuiLoading, setXuiLoading] = useState(true);
  const [inactiveDays, setInactiveDays] = useState(30);
  const [inactivePayers, setInactivePayers] = useState<InactivePayerRow[]>([]);
  const [recentUsers, setRecentUsers] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);

  const loadXui = useCallback(async () => {
    setXuiLoading(true);
    try {
      const data = await api.xuiStatus();
      setXui(data);
      setXuiError(data.ok ? null : data.error ?? 'Ошибка 3X-UI');
    } catch (e) {
      setXui(null);
      setXuiError(e instanceof Error ? e.message : 'Не удалось получить статус сервера');
    } finally {
      setXuiLoading(false);
    }
  }, []);

  const loadInactive = useCallback(async (days: number) => {
    const rows = await api.inactivePayers(days, 15);
    setInactivePayers(rows);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [s, a, r, u, p, recent] = await Promise.all([
          api.stats(),
          api.analytics(),
          api.revenueStats(30),
          api.usersStats(30),
          api.plansStats(),
          api.recentUsers(8),
        ]);
        setStats(s);
        setAnalytics(a);
        setRevenue(r);
        setGrowth(u);
        setPlans(p);
        setRecentUsers(recent);
      } finally {
        setLoading(false);
      }
    })();
    loadXui();
  }, [loadXui]);

  useEffect(() => {
    loadInactive(inactiveDays).catch(() => setInactivePayers([]));
  }, [inactiveDays, loadInactive]);

  if (loading) {
    return (
      <div className="page-loading">
        <Spinner size={32} />
      </div>
    );
  }

  const u = stats?.users;
  const s = stats?.subscriptions;
  const p = stats?.payments;
  const server = xui?.server;
  const memPct = usagePct(server?.mem?.current, server?.mem?.total);
  const diskPct = usagePct(server?.disk?.current, server?.disk?.total);

  return (
    <div className="page dashboard-page">
      <header className="page-header dashboard-page__header">
        <div>
          <h1>Дашборд</h1>
          <p className="page-desc">Обзор сервиса, клиентов и состояния VPN-сервера</p>
        </div>
        {stats?.updated_at && (
          <span className="page-meta">Обновлено: {fmtDate(stats.updated_at)}</span>
        )}
      </header>

      <section className="dashboard-bento">
        <article className="card server-panel dashboard-bento__server">
          <header className="server-panel__header">
            <div className="server-panel__title">
              <Server size={20} />
              <div>
                <h3>VPN-сервер (3X-UI)</h3>
                <p>{xui?.panel?.host ?? 'Панель не подключена'}</p>
              </div>
            </div>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={loadXui}
              disabled={xuiLoading}
              aria-label="Обновить статус сервера"
            >
              <RefreshCw size={16} className={xuiLoading ? 'spin-icon' : ''} />
            </button>
          </header>

          {xuiLoading && !server ? (
            <div className="server-panel__loading"><Spinner size={24} /></div>
          ) : xuiError ? (
            <p className="banner banner--error">{xuiError}</p>
          ) : server ? (
            <div className="server-panel__body">
              <div className="server-panel__badges">
                <XrayBadge state={server.xray?.state} />
                {server.xray?.version && (
                  <Badge variant="muted">{server.xray.version}</Badge>
                )}
                {xui?.clients_count != null && (
                  <Badge variant="default">{xui.clients_count} клиентов</Badge>
                )}
                {xui?.inbounds_count != null && (
                  <Badge variant="muted">{xui.inbounds_count} inbound</Badge>
                )}
              </div>

              <div className="server-panel__metrics">
                <MetricBar
                  label="CPU"
                  pct={Math.round(server.cpu ?? 0)}
                  hint={
                    server.cpuCores
                      ? `${server.cpuCores} ядер · load ${server.loads?.[0]?.toFixed(2) ?? '—'}`
                      : undefined
                  }
                />
                <MetricBar
                  label="RAM"
                  pct={memPct}
                  hint={`${fmtBytes(server.mem?.current)} / ${fmtBytes(server.mem?.total)}`}
                />
                <MetricBar
                  label="Диск"
                  pct={diskPct}
                  hint={`${fmtBytes(server.disk?.current)} / ${fmtBytes(server.disk?.total)}`}
                />
              </div>

              <div className="server-panel__stats">
                <div>
                  <span>Uptime</span>
                  <strong>{fmtUptime(server.uptime)}</strong>
                </div>
                <div>
                  <span>TCP</span>
                  <strong>{server.tcpCount ?? '—'}</strong>
                </div>
                <div>
                  <span>Net ↑</span>
                  <strong>{fmtBytes(server.netIO?.up ?? server.netTraffic?.sent)}</strong>
                </div>
                <div>
                  <span>Net ↓</span>
                  <strong>{fmtBytes(server.netIO?.down ?? server.netTraffic?.recv)}</strong>
                </div>
              </div>
            </div>
          ) : null}
        </article>

        <div className="dashboard-bento__stats">
          {stats && (
            <div className="dashboard-stat-block">
              <p className="dashboard-stat-block__label">Сервис</p>
              <div className="dashboard-stat-group">
                <StatCard
                  label="Пользователей"
                  value={u!.total}
                  hint={`+${u!.new_24h} за 24ч · +${u!.new_7d} за 7д`}
                  icon={<Users size={22} />}
                  accent="#38bdf8"
                />
                <StatCard
                  label="Активных подписок"
                  value={s!.active}
                  hint={`${s!.pending} ожидают · ${s!.expired} истекли`}
                  icon={<Zap size={22} />}
                  accent="#818cf8"
                />
                <StatCard
                  label="Истекают завтра"
                  value={s!.expiring_tomorrow}
                  icon={<Clock size={22} />}
                  accent="#fbbf24"
                />
                <StatCard
                  label="Выручка 30д"
                  value={fmtMoney(p!.revenue_30d)}
                  hint={`${p!.count_30d} платежей`}
                  icon={<Wallet size={22} />}
                  accent="#34d399"
                />
                <StatCard
                  label="Без VPN-ключа"
                  value={p!.unfulfilled}
                  hint={`${p!.pending} ожидают оплаты`}
                  icon={<AlertTriangle size={22} />}
                  accent={p!.unfulfilled ? '#f87171' : '#64748b'}
                />
                <StatCard
                  label="Заблокировано"
                  value={u!.banned}
                  hint={`${stats.promos.active} активных промо`}
                  icon={<Ban size={22} />}
                  accent="#94a3b8"
                />
              </div>
            </div>
          )}

          {analytics && (
            <div className="dashboard-stat-block">
              <p className="dashboard-stat-block__label">Клиенты</p>
              <div className="dashboard-stat-group">
                <StatCard
                  label="Платящие клиенты"
                  value={analytics.paying_users}
                  hint={`конверсия ${fmtPct(analytics.conversion_pct)}`}
                  icon={<TrendingUp size={22} />}
                  accent="#34d399"
                />
                <StatCard
                  label="Средний LTV"
                  value={fmtMoney(analytics.avg_ltv)}
                  hint={`средний чек ${fmtMoney(analytics.avg_payment)}`}
                  icon={<Wallet size={22} />}
                  accent="#38bdf8"
                />
                <StatCard
                  label="Повторные оплаты"
                  value={analytics.repeat_payers}
                  hint={`${fmtPct(analytics.repeat_rate_pct)} клиентов`}
                  icon={<Repeat size={22} />}
                  accent="#818cf8"
                />
                <StatCard
                  label="Без оплат"
                  value={analytics.never_paid}
                  hint="зарегистрировались, не платили"
                  icon={<UserMinus size={22} />}
                  accent="#94a3b8"
                />
                <StatCard
                  label="Не платили 30+ дн."
                  value={analytics.inactive_payers.days_30}
                  hint={`60д: ${analytics.inactive_payers.days_60} · 90д: ${analytics.inactive_payers.days_90}`}
                  icon={<Activity size={22} />}
                  accent="#f87171"
                />
                <StatCard
                  label="Истекли (были клиентами)"
                  value={analytics.expired_paid}
                  hint={`${analytics.active_paying} активных с оплатой`}
                  icon={<Clock size={22} />}
                  accent="#fbbf24"
                />
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="dashboard-charts">
        <article className="card chart-card">
          <h3>Выручка за 30 дней</h3>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={revenue}>
                <defs>
                  <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={(v) => String(v).slice(5)} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    background: '#1a2234',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 8,
                  }}
                  formatter={(v: number) => [fmtMoney(v), 'Сумма']}
                />
                <Area type="monotone" dataKey="revenue" stroke="#38bdf8" fill="url(#revGrad)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="card chart-card">
          <h3>Новые пользователи</h3>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={growth}>
                <defs>
                  <linearGradient id="usrGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#818cf8" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#818cf8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={(v) => String(v).slice(5)} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: '#1a2234',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 8,
                  }}
                />
                <Area type="monotone" dataKey="count" stroke="#818cf8" fill="url(#usrGrad)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="card chart-card chart-card--plans">
          <h3>Распределение тарифов</h3>
          <div className="chart-wrap chart-wrap--pie">
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={plans}
                  dataKey="count"
                  nameKey="plan"
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={88}
                  paddingAngle={3}
                >
                  {plans.map((entry, i) => (
                    <Cell key={entry.plan} fill={PLAN_COLORS[i % PLAN_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: '#1a2234',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 8,
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="plan-legend">
              {plans.map((pl, i) => (
                <span key={pl.plan} className="plan-legend-item">
                  <i style={{ background: PLAN_COLORS[i % PLAN_COLORS.length] }} />
                  {pl.plan} · {pl.count}
                </span>
              ))}
            </div>
          </div>
        </article>
      </section>

      <section className="dashboard-tables">
        <article className="card table-card">
          <header className="dashboard-table-header">
            <div>
              <h3>Давно не оплачивали</h3>
              <p>Клиенты с успешными платежами, но без оплаты давно</p>
            </div>
            <select
              value={inactiveDays}
              onChange={(e) => setInactiveDays(Number(e.target.value))}
              className="toolbar-field toolbar-field--select"
              aria-label="Период без оплаты"
            >
              {INACTIVE_DAYS_OPTIONS.map((d) => (
                <option key={d} value={d}>Более {d} дней</option>
              ))}
            </select>
          </header>
          <div className="table-wrap table-wrap--desktop">
            <table>
              <thead>
                <tr>
                  <th>Клиент</th>
                  <th>Подписка</th>
                  <th>Последняя оплата</th>
                  <th>Дней назад</th>
                  <th>Потрачено</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {inactivePayers.length === 0 ? (
                  <tr><td colSpan={6} className="empty-cell">Нет таких клиентов</td></tr>
                ) : (
                  inactivePayers.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <div className="cell-user">
                          <strong>{row.full_name}</strong>
                          <span className="cell-muted">
                            {row.username ? `@${row.username}` : `#${row.telegram_id}`}
                          </span>
                        </div>
                      </td>
                      <td className={daysLeftClass(row.subscription)}>
                        {row.subscription?.status ?? '—'}
                        {row.subscription?.plan ? ` · ${row.subscription.plan}` : ''}
                      </td>
                      <td>{fmtDate(row.last_paid_at)}</td>
                      <td className="text-danger">{row.days_since_payment}</td>
                      <td>{fmtMoney(row.total_spent)}</td>
                      <td className="actions">
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={() => setSelectedUserId(row.id)}
                        >
                          Карточка
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <ul className="mobile-data-list" aria-label="Клиенты без оплат">
            {inactivePayers.length === 0 ? (
              <li><p className="mobile-data-card__empty">Нет таких клиентов</p></li>
            ) : (
              inactivePayers.map((row) => (
                <li key={row.id} className="mobile-data-card">
                  <div className="mobile-data-card__head">
                    <div className="cell-user">
                      <strong>{row.full_name}</strong>
                      <span className="cell-muted">
                        {row.username ? `@${row.username}` : `#${row.telegram_id}`}
                      </span>
                    </div>
                    <span className={`badge badge--muted ${daysLeftClass(row.subscription)}`}>
                      {row.subscription?.status ?? '—'}
                    </span>
                  </div>
                  <dl className="mobile-data-card__rows">
                    <div className="mobile-data-card__row">
                      <dt>Тариф</dt>
                      <dd>{row.subscription?.plan ?? '—'}</dd>
                    </div>
                    <div className="mobile-data-card__row">
                      <dt>Последняя оплата</dt>
                      <dd>{fmtDate(row.last_paid_at)}</dd>
                    </div>
                    <div className="mobile-data-card__row">
                      <dt>Дней назад</dt>
                      <dd className="text-danger">{row.days_since_payment}</dd>
                    </div>
                    <div className="mobile-data-card__row">
                      <dt>Потрачено</dt>
                      <dd>{fmtMoney(row.total_spent)}</dd>
                    </div>
                  </dl>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => setSelectedUserId(row.id)}
                  >
                    Карточка
                  </button>
                </li>
              ))
            )}
          </ul>
        </article>

        <article className="card table-card">
          <header className="dashboard-table-header">
            <div>
              <h3>Новые пользователи</h3>
              <p>Последние регистрации и статус подписки</p>
            </div>
          </header>
          <div className="table-wrap table-wrap--desktop">
            <table>
              <thead>
                <tr>
                  <th>Клиент</th>
                  <th>Регистрация</th>
                  <th>Подписка</th>
                  <th>Осталось</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {recentUsers.length === 0 ? (
                  <tr><td colSpan={5} className="empty-cell">Нет данных</td></tr>
                ) : (
                  recentUsers.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <div className="cell-user">
                          <strong>{row.full_name}</strong>
                          <span className="cell-muted">
                            {row.username ? `@${row.username}` : `#${row.telegram_id}`}
                          </span>
                        </div>
                      </td>
                      <td>{fmtDate(row.created_at)}</td>
                      <td>{row.subscription?.status ?? '—'}</td>
                      <td className={daysLeftClass(row.subscription)}>{fmtDaysLeft(row.subscription)}</td>
                      <td className="actions">
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={() => setSelectedUserId(row.id)}
                        >
                          Карточка
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <ul className="mobile-data-list" aria-label="Новые пользователи">
            {recentUsers.length === 0 ? (
              <li><p className="mobile-data-card__empty">Нет данных</p></li>
            ) : (
              recentUsers.map((row) => (
                <li key={row.id} className="mobile-data-card">
                  <div className="mobile-data-card__head">
                    <div className="cell-user">
                      <strong>{row.full_name}</strong>
                      <span className="cell-muted">
                        {row.username ? `@${row.username}` : `#${row.telegram_id}`}
                      </span>
                    </div>
                    <span className="badge badge--muted">{row.subscription?.status ?? '—'}</span>
                  </div>
                  <dl className="mobile-data-card__rows">
                    <div className="mobile-data-card__row">
                      <dt>Регистрация</dt>
                      <dd>{fmtDate(row.created_at)}</dd>
                    </div>
                    <div className="mobile-data-card__row">
                      <dt>Осталось</dt>
                      <dd className={daysLeftClass(row.subscription)}>{fmtDaysLeft(row.subscription)}</dd>
                    </div>
                  </dl>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => setSelectedUserId(row.id)}
                  >
                    Карточка
                  </button>
                </li>
              ))
            )}
          </ul>
        </article>
      </section>

      <UserCardModal
        userId={selectedUserId}
        onClose={() => setSelectedUserId(null)}
        onRefresh={() => {
          loadInactive(inactiveDays).catch(() => setInactivePayers([]));
          api.recentUsers(8).then(setRecentUsers).catch(() => {});
        }}
        onXuiSync={(id) => {
          setSelectedUserId(null);
          onXuiSync(id);
        }}
        onToast={onToast}
      />
    </div>
  );
}
