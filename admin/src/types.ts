export interface DashboardStats {
  users: {
    total: number;
    new_24h: number;
    new_7d: number;
    banned: number;
  };
  subscriptions: {
    active: number;
    pending: number;
    expired: number;
    expiring_tomorrow: number;
  };
  payments: {
    revenue_30d: number;
    count_30d: number;
    unfulfilled: number;
    pending: number;
  };
  promos: { active: number };
  promotions?: { active: number };
  updated_at?: string;
}

export interface RevenuePoint {
  date: string;
  count: number;
  revenue: number;
}

export interface UsersGrowthPoint {
  date: string;
  count: number;
}

export interface PlanStat {
  plan: string;
  count: number;
}

export interface ClientAnalytics {
  paying_users: number;
  never_paid: number;
  repeat_payers: number;
  repeat_rate_pct: number;
  conversion_pct: number;
  total_revenue: number;
  revenue_30d: number;
  avg_ltv: number;
  avg_payment: number;
  active_paying: number;
  expired_paid: number;
  inactive_payers: {
    days_30: number;
    days_60: number;
    days_90: number;
  };
}

export interface InactivePayerRow extends UserRow {
  last_paid_at: string | null;
  days_since_payment: number;
  payments_count: number;
  total_spent: number;
}

export interface XuiServerMetrics {
  cpu?: number;
  cpuCores?: number;
  logicalPro?: number;
  mem?: { current?: number; total?: number };
  swap?: { current?: number; total?: number };
  disk?: { current?: number; total?: number };
  netIO?: { up?: number; down?: number };
  netTraffic?: { sent?: number; recv?: number };
  xray?: { state?: string; version?: string; errorMsg?: string };
  uptime?: number;
  loads?: number[];
  tcpCount?: number;
  udpCount?: number;
  publicIP?: { ipv4?: string; ipv6?: string };
}

export interface XuiStatusResponse {
  ok: boolean;
  error?: string;
  panel?: {
    host?: string;
    sub_base_url?: string;
  };
  server?: XuiServerMetrics;
  inbounds_count?: number;
  clients_count?: number;
}

export interface SubscriptionSummary {
  plan: string | null;
  status: string | null;
  expires_at: string | null;
  days_left: number;
  is_active: boolean;
  is_expired: boolean;
  subscription_id?: number;
}

export interface UserRow {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  full_name: string;
  language_code: string | null;
  is_banned: boolean;
  referrer_id: number | null;
  created_at: string | null;
  last_seen: string | null;
  subscription?: SubscriptionSummary;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

export interface TelegramProfile {
  available?: boolean;
  error?: string;
  id?: number;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  bio?: string | null;
  language_code?: string | null;
  is_premium?: boolean;
  has_photo?: boolean;
  photo_url?: string | null;
  profile_link?: string | null;
}

export interface UserStats {
  payments_total: number;
  payments_succeeded: number;
  total_spent: number;
  referrals_count: number;
  subscriptions_total: number;
}

export interface SubscriptionRow {
  id: number;
  user_id: number;
  telegram_id: number;
  plan: string;
  status: string;
  vpn_uuid: string | null;
  vpn_email: string | null;
  vpn_sub_id: string | null;
  vpn_key: string | null;
  inbound_id: number | null;
  started_at: string | null;
  expires_at: string | null;
  months_paid: number | null;
  promo_code: string | null;
  discount_pct: number | null;
  limit_ip: number;
  traffic_gb: number | null;
  days_left: number;
  is_active: boolean;
  is_expired: boolean;
  vpn_disabled_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PaymentRow {
  id: number;
  user_id: number;
  subscription_id: number | null;
  telegram_id: number | null;
  provider: string | null;
  order_id: string | null;
  yookassa_id: string | null;
  payment_url: string | null;
  description: string | null;
  amount: number;
  paid_amount: number | null;
  currency: string;
  status: string;
  provider_status: string | null;
  plan: string | null;
  months: number | null;
  promo_code: string | null;
  promotion_id: number | null;
  original_amount: number | null;
  discount_amount: number | null;
  created_at: string | null;
  paid_at: string | null;
  fulfilled_at: string | null;
  is_fulfilled: boolean;
}

export interface PromoRow {
  id: number;
  code: string;
  name: string | null;
  description: string | null;
  discount_pct: number | null;
  discount_amount: number | null;
  plans: string[] | null;
  months: string[] | null;
  min_amount: number | null;
  max_uses: number | null;
  uses_count: number;
  one_per_user: boolean;
  is_active: boolean;
  is_valid: boolean;
  expires_at: string | null;
  created_at: string | null;
}

export interface PromotionRow {
  id: number;
  name: string;
  description: string | null;
  discount_pct: number | null;
  discount_amount: number | null;
  plans: string[] | null;
  months: string[] | null;
  min_amount: number | null;
  new_users_only: boolean;
  starts_at: string | null;
  ends_at: string | null;
  is_active: boolean;
  is_valid: boolean;
  priority: number;
  stackable_with_promo: boolean;
  created_at: string | null;
}

export interface UserDetail extends UserRow {
  stats: UserStats;
  subscriptions: SubscriptionRow[];
  payments: PaymentRow[];
  telegram_profile: TelegramProfile | null;
  subscription: SubscriptionSummary;
}

export interface AdminConfig {
  plans: Record<string, unknown>;
  months_labels: Record<string, string>;
  subscription_statuses: string[];
  payment_statuses: string[];
  plan_types: string[];
}

export interface XuiSyncResult {
  processed: number;
  updated: number;
  imported?: number;
  deleted: number;
  skipped: number;
  errors: number;
  dry_run?: boolean;
  items?: Array<{
    user_id: number;
    telegram_id: number;
    action: string;
    message?: string;
  }>;
}

export interface XuiPushResult {
  ok: boolean;
  message?: string;
  skipped?: boolean;
}

export interface SubscriptionUpdatePayload {
  status?: string;
  plan?: string;
  expires_at?: string;
  extend_days?: number;
  extend_months?: number;
  limit_ip?: number;
  disable?: boolean;
}

export interface BroadcastTarget {
  id: string;
  label: string;
}

export interface BroadcastRow {
  id: number;
  name: string | null;
  text: string;
  target: string;
  target_label: string;
  status: 'scheduled' | 'sending' | 'sent' | 'cancelled' | 'failed';
  send_at: string | null;
  sent: boolean;
  sent_count: number;
  failed_count: number;
  target_count: number | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_at: string | null;
}
