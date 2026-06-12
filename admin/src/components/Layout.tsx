import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  CreditCard,
  Tag,
  Percent,
  LogOut,
  Server,
} from 'lucide-react';
import { Logo } from './ui';
import { useAuth } from '../context/AuthContext';

const nav = [
  { to: '/', icon: LayoutDashboard, label: 'Дашборд' },
  { to: '/users', icon: Users, label: 'Пользователи' },
  { to: '/payments', icon: CreditCard, label: 'Платежи' },
  { to: '/promotions', icon: Percent, label: 'Акции' },
  { to: '/promos', icon: Tag, label: 'Промокоды' },
];

interface LayoutProps {
  onXuiSync: () => void;
}

export function Layout({ onXuiSync }: LayoutProps) {
  const { brand, logout } = useAuth();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Logo brand={brand.replace(/\s*VPN\s*$/i, '') || 'SkyPath'} size={36} />
        </div>
        <nav className="sidebar-nav">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}
            >
              <Icon size={20} strokeWidth={1.75} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button
            type="button"
            className="nav-link nav-link--action"
            onClick={onXuiSync}
          >
            <Server size={20} strokeWidth={1.75} />
            <span>Синхр. 3X-UI</span>
          </button>
          <button type="button" className="nav-link nav-link--action nav-link--danger" onClick={() => logout()}>
            <LogOut size={20} strokeWidth={1.75} />
            <span>Выйти</span>
          </button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
