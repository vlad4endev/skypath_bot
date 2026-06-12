const LOCALE_MAP: Record<string, string> = {
  ru: 'ru-RU',
  en: 'en-US',
  hi: 'hi-IN',
  ar: 'ar-SA',
};

export function formatDate(iso: string | null | undefined, locale = 'ru'): string {
  if (!iso) return '—';
  try {
    const intlLocale = LOCALE_MAP[locale] || 'en-US';
    return new Intl.DateTimeFormat(intlLocale, {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function formatBytes(bytes: number | undefined): string {
  if (bytes == null || bytes <= 0) return '0 Б';
  const units = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

export function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text);
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  ta.remove();
  return Promise.resolve();
}

export function buildConnectUrl(subUrl: string, app: 'happ' | 'v2ray'): string {
  const encoded = encodeURIComponent(subUrl);
  if (app === 'happ') {
    return `happ://add/${encoded}`;
  }
  return `v2raytun://import/${encoded}`;
}

export function getInitials(name: string | null | undefined): string {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}
