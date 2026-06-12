export function fmtMoney(amount: number, currency = 'RUB'): string {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function fmtExpiry(sub: { expires_at?: string | null; is_expired?: boolean; days_left?: number; is_active?: boolean } | null | undefined): string {
  if (!sub?.expires_at) return '—';
  const label = fmtDate(sub.expires_at);
  if (sub.is_expired) return `${label} · истекло`;
  if (sub.is_active && sub.days_left != null) return `${label} · ${sub.days_left} дн.`;
  return label;
}

function daysWord(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return 'дней';
  if (mod10 === 1) return 'день';
  if (mod10 >= 2 && mod10 <= 4) return 'дня';
  return 'дней';
}

/** Оставшиеся дни подписки (без даты/времени). */
export function fmtDaysLeft(
  sub: { expires_at?: string | null; is_expired?: boolean; days_left?: number } | null | undefined,
): string {
  if (!sub?.expires_at) return '—';
  if (subIsExpired(sub)) return 'истекло';
  if (sub.days_left == null) return '—';
  return `${sub.days_left} ${daysWord(sub.days_left)}`;
}

/** Класс цвета: зелёный при >3 дн., красный при ≤3 дн. или истекло. */
export function daysLeftClass(
  sub: { expires_at?: string | null; is_expired?: boolean; days_left?: number; status?: string | null } | null | undefined,
): string {
  if (!sub?.expires_at) return '';
  if (subIsExpired(sub)) return 'text-danger';
  if (sub.days_left == null) return '';
  return sub.days_left <= 3 ? 'text-danger' : 'text-success';
}

export function toDatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function subIsExpired(sub: { is_expired?: boolean; status?: string | null } | null | undefined): boolean {
  if (!sub) return false;
  return !!sub.is_expired || sub.status === 'ИСТЕКЛА' || sub.status === 'ЗАБЛОКИРОВАНА';
}

export function pagesCount(total: number, perPage: number): number {
  return Math.max(1, Math.ceil(total / perPage));
}

export function fmtBytes(bytes: number | undefined | null): string {
  if (bytes == null || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function fmtUptime(seconds: number | undefined | null): string {
  if (!seconds) return '—';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}д ${h}ч`;
  if (h > 0) return `${h}ч ${m}м`;
  return `${m}м`;
}

export function fmtPct(value: number | undefined | null, digits = 1): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${value.toFixed(digits)}%`;
}

export function userInitials(
  first?: string | null,
  last?: string | null,
  full?: string | null,
): string {
  const name = (first || full || '?').trim();
  const parts = name.split(/\s+/);
  return (parts[0][0] + (last?.[0] || parts[1]?.[0] || '')).toUpperCase();
}
