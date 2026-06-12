import { useEffect, useState, type ReactNode } from 'react';

interface LogoProps {
  size?: number;
  showText?: boolean;
  brand?: string;
}

export function Logo({ size = 40, showText = true, brand = 'SkyPath' }: LogoProps) {
  return (
    <div className="logo" style={{ '--logo-size': `${size}px` } as React.CSSProperties}>
      <svg
        className="logo-mark"
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
      >
        <defs>
          <linearGradient id="skyGrad" x1="8" y1="4" x2="40" y2="44" gradientUnits="userSpaceOnUse">
            <stop stopColor="#38bdf8" />
            <stop offset="0.5" stopColor="#6366f1" />
            <stop offset="1" stopColor="#818cf8" />
          </linearGradient>
          <linearGradient id="pathGrad" x1="14" y1="28" x2="34" y2="38" gradientUnits="userSpaceOnUse">
            <stop stopColor="#e0f2fe" />
            <stop offset="1" stopColor="#c7d2fe" />
          </linearGradient>
        </defs>
        <rect x="4" y="4" width="40" height="40" rx="12" fill="url(#skyGrad)" opacity="0.15" />
        <path
          d="M24 8C16 8 10 14 10 22c0 6 4 11 9 13l5 2 5-2c5-2 9-7 9-13 0-8-6-14-14-14z"
          fill="url(#skyGrad)"
        />
        <path
          d="M14 30c3-4 7-6 10-6s7 2 10 6"
          stroke="url(#pathGrad)"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        <circle cx="24" cy="20" r="3" fill="#f0f9ff" opacity="0.9" />
      </svg>
      {showText && (
        <div className="logo-text">
          <span className="logo-brand">{brand}</span>
          <span className="logo-tag">Admin</span>
        </div>
      )}
    </div>
  );
}

interface SpinnerProps {
  size?: number;
}

export function Spinner({ size = 24 }: SpinnerProps) {
  return (
    <div
      className="spinner"
      style={{ width: size, height: size }}
      role="status"
      aria-label="Загрузка"
    />
  );
}

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  wide?: boolean;
  children: ReactNode;
  footer?: ReactNode;
}

export function Modal({ open, onClose, title, wide, children, footer }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div
        className={`modal ${wide ? 'modal--wide' : ''}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <header className="modal-header">
          <h2 id="modal-title">{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Закрыть">
            ×
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </div>
    </div>
  );
}

interface BadgeProps {
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'muted';
  children: ReactNode;
}

export function Badge({ variant = 'default', children }: BadgeProps) {
  return <span className={`badge badge--${variant}`}>{children}</span>;
}

interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
  icon?: ReactNode;
  accent?: string;
}

export function StatCard({ label, value, hint, icon, accent }: StatCardProps) {
  return (
    <article className="stat-card" style={accent ? { '--stat-accent': accent } as React.CSSProperties : undefined}>
      <div className="stat-card-top">
        {icon && <div className="stat-card-icon">{icon}</div>}
        <span className="stat-card-label">{label}</span>
      </div>
      <div className="stat-card-value">{value}</div>
      {hint && <div className="stat-card-hint">{hint}</div>}
    </article>
  );
}

interface PaginationProps {
  page: number;
  pages: number;
  onPage: (p: number) => void;
}

export function Pagination({ page, pages, onPage }: PaginationProps) {
  if (pages <= 1) return null;
  return (
    <nav className="pagination" aria-label="Страницы">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ← Назад
      </button>
      <span>
        {page} / {pages}
      </span>
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Вперёд →
      </button>
    </nav>
  );
}

interface EmptyStateProps {
  title: string;
  description?: string;
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <p className="empty-state-title">{title}</p>
      {description && <p className="empty-state-desc">{description}</p>}
    </div>
  );
}

interface ToastProps {
  message: string;
  type?: 'success' | 'error' | 'info';
  onClose: () => void;
}

export function Toast({ message, type = 'info', onClose }: ToastProps) {
  return (
    <div className={`toast toast--${type}`} role="alert">
      <span>{message}</span>
      <button type="button" className="toast-close" onClick={onClose} aria-label="Закрыть">
        ×
      </button>
    </div>
  );
}

export function useToast() {
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  const show = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  const ToastEl = toast ? (
    <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
  ) : null;

  return { show, ToastEl };
}
