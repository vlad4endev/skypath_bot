import { NavLink, Outlet } from 'react-router-dom';
import {
  Home,
  KeyRound,
  CreditCard,
  HelpCircle,
  User,
} from 'lucide-react';
import { Logo } from './ui';
import { useAuth } from '../context/AuthContext';
import { useI18n } from '../i18n/I18nContext';

export function Layout() {
  const { brand, user } = useAuth();
  const { t } = useI18n();

  const NAV = [
    { to: '/app', icon: Home, label: t('nav_home'), end: true },
    { to: '/app/keys', icon: KeyRound, label: t('nav_keys') },
    { to: '/app/plans', icon: CreditCard, label: t('nav_plans') },
    { to: '/app/support', icon: HelpCircle, label: t('nav_support') },
    { to: '/app/profile', icon: User, label: t('nav_profile') },
  ];

  return (
    <div className="layout">
      <div className="main-wrap">
        <header className="topbar">
          <Logo brand={brand} size={36} />
          <div className="topbar-spacer" />
          <NavLink
            to="/app/profile"
            className={({ isActive }) => `topbar-profile${isActive ? ' active' : ''}`}
            aria-label={t('nav_profile')}
          >
            <div className="user-avatar user-avatar--sm">
              {user?.full_name?.[0]?.toUpperCase() || '?'}
            </div>
          </NavLink>
        </header>

        <main className="main-content" id="main-content">
          <Outlet />
        </main>

        <nav className="bottom-nav" aria-label="Нижняя навигация">
          {NAV.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `bottom-nav-item ${isActive ? 'active' : ''}`}
              aria-label={label}
            >
              <Icon size={22} strokeWidth={2} aria-hidden />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
