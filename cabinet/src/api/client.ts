const TOKEN_KEY = 'cabinet_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(path, { ...init, headers, credentials: 'same-origin' });
  const text = await res.text();
  let data: Record<string, unknown> | null = null;
  if (text) {
    try {
      data = JSON.parse(text) as Record<string, unknown>;
    } catch {
      data = { message: text };
    }
  }

  if (!res.ok) {
    const msg =
      (typeof data?.message === 'string' && data.message) ||
      (typeof data?.error === 'string' && data.error) ||
      res.statusText;
    const code = typeof data?.error === 'string' ? data.error : undefined;
    throw new ApiError(msg, res.status, code);
  }
  return data as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ ok: boolean; token: string }>('/cabinet/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  register: (payload: {
    email: string;
    password: string;
    password_confirm?: string;
    first_name?: string;
    locale?: string;
  }) =>
    request<{ ok: boolean; token: string; message?: string }>('/cabinet/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  publicPlans: () =>
    request<{
      brand_name: string;
      plans: import('../types').DashboardData['plans'];
      locale: string;
    }>('/cabinet/api/plans/public'),

  logout: () =>
    request<{ ok: boolean }>('/cabinet/api/auth/logout', { method: 'POST' }),

  me: () =>
    request<{
      ok: boolean;
      brand: string;
      locale?: string;
      i18n?: import('../types').I18nApiBundle;
      user: { full_name: string | null; email: string | null };
    }>('/cabinet/api/auth/me'),

  setLocale: (locale: string) =>
    request<{ ok: boolean; locale: string; i18n: import('../types').I18nApiBundle; message?: string }>(
      '/cabinet/api/locale',
      { method: 'POST', body: JSON.stringify({ locale }) },
    ),

  config: () => request<import('../types').AppConfig & {
    terms_url?: string;
    privacy_url?: string;
  }>('/cabinet/api/config'),

  dashboard: () => request<import('../types').DashboardData>('/cabinet/api/dashboard'),

  previewDiscount: (plan: string) =>
    request<{ plan: string; months: Record<string, { base_price: number; final_price: number; discount_total: number; discount_label?: string }> }>(
      `/cabinet/api/discount/preview?plan=${encodeURIComponent(plan)}`,
    ),

  validatePromo: (plan: string, months: number, promoCode: string) =>
    request<{
      valid: boolean;
      base_price?: number;
      final_price?: number;
      discount_total?: number;
      discount_label?: string;
      error?: string;
    }>('/cabinet/api/promo/validate', {
      method: 'POST',
      body: JSON.stringify({ plan, months, promo_code: promoCode }),
    }),

  pay: (payload: {
    plan: string;
    months: number;
    price: number;
    promo_code?: string;
  }) =>
    request<import('../types').PayResult>('/cabinet/api/pay', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  provision: () =>
    request<{ subscription_url: string; message: string }>('/cabinet/api/provision', {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  paymentStatus: (orderId: string) =>
    request<{
      order_id: string;
      status: string;
      subscription_url: string | null;
      fulfilled: boolean;
    }>(`/cabinet/api/payment/${encodeURIComponent(orderId)}/status`),
};
