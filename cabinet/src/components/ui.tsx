interface LogoProps {
  size?: number;
  showText?: boolean;
  brand?: string;
}

export function Logo({ size = 40, showText = true, brand = 'SkyPath' }: LogoProps) {
  return (
    <div className="logo">
      <svg
        className="logo-mark"
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        aria-hidden
      >
        <defs>
          <linearGradient id="cabGrad" x1="8" y1="4" x2="40" y2="44" gradientUnits="userSpaceOnUse">
            <stop stopColor="#c4ceff" />
            <stop offset="0.5" stopColor="#8a9cfe" />
            <stop offset="1" stopColor="#5b6fd6" />
          </linearGradient>
        </defs>
        <rect x="4" y="4" width="40" height="40" rx="12" fill="url(#cabGrad)" opacity="0.15" />
        <path
          d="M24 8C16 8 10 14 10 22c0 6 4 11 9 13l5 2 5-2c5-2 9-7 9-13 0-8-6-14-14-14z"
          fill="url(#cabGrad)"
        />
        <text
          x="24"
          y="26"
          textAnchor="middle"
          fontFamily="Inter, system-ui, sans-serif"
          fontSize="14"
          fontWeight="900"
          fill="#ffffff"
        >
          S
        </text>
      </svg>
      {showText && (
        <div className="logo-text">
          <span className="logo-brand">{brand}</span>
          <span className="logo-tag">VPN</span>
        </div>
      )}
    </div>
  );
}

export function Spinner({ size = 24 }: { size?: number }) {
  return (
    <div
      className="spinner"
      style={{ width: size, height: size }}
      role="status"
      aria-label="Загрузка"
    />
  );
}

interface ToastProps {
  message: string;
  error?: boolean;
  onClose: () => void;
}

export function Toast({ message, error, onClose }: ToastProps) {
  return (
    <div className={`toast ${error ? 'toast--error' : ''}`} role="alert">
      <span>{message}</span>
      <button type="button" className="toast-close" onClick={onClose} aria-label="Закрыть">
        ×
      </button>
    </div>
  );
}

interface StatusBadgeProps {
  active: boolean;
  label?: string;
}

export function StatusBadge({ active, label }: StatusBadgeProps) {
  return (
    <span className={`badge ${active ? 'badge--success' : 'badge--muted'}`}>
      {label || (active ? 'Активна' : 'Неактивна')}
    </span>
  );
}

interface TrafficRingProps {
  used?: number;
  limit?: number;
  size?: number;
}

export function TrafficRing({ used = 0, limit = 0, size = 120 }: TrafficRingProps) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const r = (size - 12) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;

  return (
    <div className="traffic-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="rgba(138,156,254,0.12)"
          strokeWidth="8"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="url(#ringGrad)"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <defs>
          <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
            <stop stopColor="#8a9cfe" />
            <stop offset="1" stopColor="#6ecf8a" />
          </linearGradient>
        </defs>
      </svg>
      <div className="traffic-ring__label">
        <strong>{limit > 0 ? `${Math.round(pct)}%` : '∞'}</strong>
        <span>трафик</span>
      </div>
    </div>
  );
}
