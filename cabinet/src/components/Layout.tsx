import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  Globe,
  Home,
  KeyRound,
  CreditCard,
  HelpCircle,
  LogOut,
  Menu,
  X,
} from 'lucide-react';
import { useState } from 'react';
import { Logo } from './ui';
import { useAuth } from '../context/AuthContext';
import { useI18n } from '../i18n/I18nContext';

export function Layout() {
  const { brand, user, logout } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const NAV = [
    { to: '/', icon: Home, label: t('nav_home'), end: true },
    { to: '/keys', icon: KeyRound, label: t('nav_keys') },
    { to: '/plans', icon: CreditCard, label: t('nav_plans') },
    { to: '/support', icon: HelpCircle, label: t('nav_support') },
    { to: '/language', icon: Globe, label: t('nav_language') },
  ];

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="layout">
      <div
        className={`sidebar-backdrop ${sidebarOpen ? 'visible' : ''}`}
        onClick={() => setSidebarOpen(false)}
        aria-hidden
      />

      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-head">
          <Logo brand={brand} size={44} />
          <button
            type="button"
            className="icon-btn sidebar-close"
            onClick={() => setSidebarOpen(false)}
            aria-label={t('close_menu')}
          >
            <X size={20} />
          </button>
        </div>

        <nav className="sidebar-nav">
          {NAV.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              onClick={() => setSidebarOpen(false)}
            >
              <Icon size={20} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="user-chip">
            <div className="user-avatar">{user?.full_name?.[0]?.toUpperCase() || '?'}</div>
            <div className="user-meta">
              <strong>{user?.full_name || t('user')}</strong>
              <span>{user?.email}</span>
            </div>
          </div>
          <button type="button" className="btn btn--ghost btn--block" onClick={handleLogout}>
            <LogOut size={18} />
            {t('logout')}
          </button>
        </div>
      </aside>

      <div className="main-wrap">
        <header className="topbar">
          <button
            type="button"
            className="icon-btn menu-btn"
            onClick={() => setSidebarOpen(true)}
            aria-label={t('menu')}
          >
            <Menu size={22} />
          </button>
          <Logo showText={false} size={36} />
          <div className="topbar-spacer" />
        </header>

        <main className="main-content">
          <Outlet />
        </main>

        <nav className="bottom-nav">
          {NAV.filter(({ to }) => to !== '/language').map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `bottom-nav-item ${isActive ? 'active' : ''}`}
            >
              <Icon size={22} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
