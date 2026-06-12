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

export function userInitials(
  first?: string | null,
  last?: string | null,
  full?: string | null,
): string {
  const name = (first || full || '?').trim();
  const parts = name.split(/\s+/);
  return (parts[0][0] + (last?.[0] || parts[1]?.[0] || '')).toUpperCase();
}
