import type {
  AdminConfig,
  DashboardStats,
  Paginated,
  PaymentRow,
  PlanStat,
  PromoRow,
  RevenuePoint,
  SubscriptionRow,
  SubscriptionUpdatePayload,
  UserDetail,
  UserRow,
  UsersGrowthPoint,
  XuiSyncResult,
} from '../types';

const TOKEN_KEY = 'admin_token';

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
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
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
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: text };
    }
  }

  if (!res.ok) {
    const msg =
      (data as { error?: string })?.error ||
      (data as { detail?: string })?.detail ||
      res.statusText;
    throw new ApiError(msg, res.status);
  }
  return data as T;
}

export const api = {
  login: (password: string) =>
    request<{ ok: boolean; token: string }>('/admin/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),

  logout: () => request<{ ok: boolean }>('/admin/api/auth/logout', { method: 'POST' }),

  me: () => request<{ ok: boolean; brand: string }>('/admin/api/auth/me'),

  config: () => request<AdminConfig>('/admin/api/config'),

  stats: () => request<DashboardStats>('/admin/api/stats'),

  revenueStats: (days = 30) =>
    request<RevenuePoint[]>(`/admin/api/stats/revenue?days=${days}`),

  usersStats: (days = 30) =>
    request<UsersGrowthPoint[]>(`/admin/api/stats/users?days=${days}`),

  plansStats: () => request<PlanStat[]>('/admin/api/stats/plans'),

  users: (page = 1, search = '', banned = '') => {
    const params = new URLSearchParams({
      page: String(page),
      per_page: '20',
      search,
    });
    if (banned) params.set('banned', banned);
    return request<Paginated<UserRow>>(`/admin/api/users?${params}`);
  },

  userDetail: (id: number) => request<UserDetail>(`/admin/api/users/${id}`),

  banUser: (id: number, is_banned: boolean) =>
    request<UserRow>(`/admin/api/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_banned }),
    }),

  deleteUser: (id: number) =>
    request<{ ok: boolean }>(`/admin/api/users/${id}`, { method: 'DELETE' }),

  syncUserXui: (id: number, body: { dry_run?: boolean; delete_missing?: boolean }) =>
    request<XuiSyncResult>(`/admin/api/users/${id}/sync-xui`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  subscription: (id: number) =>
    request<SubscriptionRow>(`/admin/api/subscriptions/${id}`),

  updateSubscription: (id: number, payload: SubscriptionUpdatePayload) =>
    request<SubscriptionRow & { xui_sync?: { ok: boolean; message?: string; skipped?: boolean } }>(
      `/admin/api/subscriptions/${id}`,
      { method: 'PATCH', body: JSON.stringify(payload) },
    ),

  deleteSubscription: (id: number) =>
    request<{ ok: boolean }>(`/admin/api/subscriptions/${id}`, { method: 'DELETE' }),

  payments: (page = 1, search = '', status = '', unfulfilled = false) => {
    const params = new URLSearchParams({ page: String(page), per_page: '20', search });
    if (status) params.set('status', status);
    if (unfulfilled) params.set('unfulfilled', 'true');
    return request<Paginated<PaymentRow>>(`/admin/api/payments?${params}`);
  },

  paymentDetail: (id: number) => request<PaymentRow>(`/admin/api/payments/${id}`),

  fulfillPayment: (id: number) =>
    request<{ ok: boolean }>(`/admin/api/payments/${id}/fulfill`, { method: 'POST' }),

  deletePayment: (id: number) =>
    request<{ ok: boolean }>(`/admin/api/payments/${id}`, { method: 'DELETE' }),

  promos: () => request<PromoRow[]>('/admin/api/promos'),

  createPromo: (data: Record<string, unknown>) =>
    request<PromoRow>('/admin/api/promos', { method: 'POST', body: JSON.stringify(data) }),

  updatePromo: (id: number, data: Record<string, unknown>) =>
    request<PromoRow>(`/admin/api/promos/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deletePromo: (id: number) =>
    request<{ ok: boolean }>(`/admin/api/promos/${id}`, { method: 'DELETE' }),

  xuiSync: (body: { dry_run?: boolean; delete_missing?: boolean }) =>
    request<XuiSyncResult>('/admin/api/xui/sync', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};
