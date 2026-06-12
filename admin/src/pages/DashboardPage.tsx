import { useEffect, useState } from 'react';
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
import { Users, Wallet, Zap, Clock, AlertTriangle, Ban } from 'lucide-react';
import { api } from '../api/client';
import type { DashboardStats, PlanStat, RevenuePoint, UsersGrowthPoint } from '../types';
import { fmtMoney } from '../utils/format';
import { Spinner, StatCard } from '../components/ui';

const PLAN_COLORS = ['#6366f1', '#38bdf8', '#34d399', '#fbbf24', '#f472b6'];

export function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [revenue, setRevenue] = useState<RevenuePoint[]>([]);
  const [growth, setGrowth] = useState<UsersGrowthPoint[]>([]);
  const [plans, setPlans] = useState<PlanStat[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [s, r, u, p] = await Promise.all([
          api.stats(),
          api.revenueStats(30),
          api.usersStats(30),
          api.plansStats(),
        ]);
        setStats(s);
        setRevenue(r);
        setGrowth(u);
        setPlans(p);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

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

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Дашборд</h1>
          <p className="page-desc">Обзор сервиса и ключевые метрики</p>
        </div>
      </header>

      {stats && (
        <section className="stat-grid">
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
        </section>
      )}

      <section className="charts-grid">
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

        <article className="card chart-card chart-card--wide">
          <h3>Распределение тарифов</h3>
          <div className="chart-wrap chart-wrap--pie">
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={plans}
                  dataKey="count"
                  nameKey="plan"
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={95}
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
    </div>
  );
}
