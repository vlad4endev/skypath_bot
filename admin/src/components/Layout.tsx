import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  CreditCard,
  Tag,
  Percent,
  Megaphone,
  LogOut,
  Server,
  Menu,
  X,
} from 'lucide-react';
import { Logo } from './ui';
import { useAuth } from '../context/AuthContext';

const nav = [
  { to: '/', icon: LayoutDashboard, label: 'Дашборд', short: 'Главная' },
  { to: '/users', icon: Users, label: 'Пользователи', short: 'Юзеры' },
  { to: '/payments', icon: CreditCard, label: 'Платежи', short: 'Оплаты' },
  { to: '/promotions', icon: Percent, label: 'Акции', short: 'Акции' },
  { to: '/promos', icon: Tag, label: 'Промокоды', short: 'Промо' },
  { to: '/broadcasts', icon: Megaphone, label: 'Рассылки', short: 'Рассыл.' },
];

interface LayoutProps {
  onXuiSync: () => void;
}

function SidebarContent({
  onXuiSync,
  onNavigate,
}: {
  onXuiSync: () => void;
  onNavigate?: () => void;
}) {
  const { brand, logout } = useAuth();

  return (
    <>
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
            onClick={onNavigate}
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
          onClick={() => {
            onNavigate?.();
            onXuiSync();
          }}
        >
          <Server size={20} strokeWidth={1.75} />
          <span>Синхр. 3X-UI</span>
        </button>
        <button
          type="button"
          className="nav-link nav-link--action nav-link--danger"
          onClick={() => logout()}
        >
          <LogOut size={20} strokeWidth={1.75} />
          <span>Выйти</span>
        </button>
      </div>
    </>
  );
}

export function Layout({ onXuiSync }: LayoutProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.body.classList.toggle('sidebar-open', menuOpen);
    return () => document.body.classList.remove('sidebar-open');
  }, [menuOpen]);

  return (
    <div className="app-shell">
      <header className="mobile-topbar">
        <button
          type="button"
          className="mobile-menu-btn"
          onClick={() => setMenuOpen((v) => !v)}
          aria-label={menuOpen ? 'Закрыть меню' : 'Открыть меню'}
          aria-expanded={menuOpen}
        >
          {menuOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
        <Logo brand="SkyPath" size={28} showText />
      </header>

      <div
        className={`sidebar-backdrop ${menuOpen ? 'sidebar-backdrop--visible' : ''}`}
        onClick={() => setMenuOpen(false)}
        aria-hidden={!menuOpen}
      />

      <aside className={`sidebar ${menuOpen ? 'sidebar--open' : ''}`}>
        <SidebarContent onXuiSync={onXuiSync} onNavigate={() => setMenuOpen(false)} />
      </aside>

      <nav className="mobile-bottom-nav" aria-label="Основная навигация">
        {nav.map(({ to, icon: Icon, short }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) => `bottom-nav-link ${isActive ? 'bottom-nav-link--active' : ''}`}
          >
            <Icon size={20} strokeWidth={1.75} />
            <span>{short}</span>
          </NavLink>
        ))}
      </nav>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
