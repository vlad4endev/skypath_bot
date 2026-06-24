export interface PlanInfo {
  key: string;
  name: string;
  description: string;
  limit_ip: number;
  traffic_gb: number;
  features: string[];
  recommended?: boolean;
  price?: number;
  days?: number;
  prices?: Record<string, number>;
}

export interface TrafficInfo {
  up?: number;
  down?: number;
  total?: number;
  limit?: number;
}

export interface SubscriptionInfo {
  id: number;
  plan: string | null;
  plan_name: string;
  status: string | null;
  is_active: boolean;
  expires_at: string | null;
  started_at: string | null;
  days_left: number;
  limit_ip: number;
  months_paid: number;
  traffic_gb: number;
  vpn_key: string | null;
  subscription_url: string | null;
  has_vpn_client: boolean;
  traffic: TrafficInfo | null;
  plan_info: PlanInfo | null;
}

export interface DashboardUser {
  telegram_id: number;
  full_name: string | null;
  username: string | null;
  email: string | null;
  member_since: string | null;
  referrals_count: number;
}

export interface DashboardData {
  brand_name: string;
  support_url: string;
  locale?: string;
  rtl?: boolean;
  i18n?: I18nApiBundle;
  user: DashboardUser | null;
  has_subscription: boolean;
  can_renew?: boolean;
  is_new_vpn_user: boolean;
  web_registered: boolean;
  subscription: SubscriptionInfo | null;
  plans: Record<string, PlanInfo> | null;
}

export interface DiscountPreview {
  months: number;
  base_price: number;
  final_price: number;
  discount_total: number;
  discount_label?: string;
}

export interface PayResult {
  error?: string;
  message?: string;
  payment_url?: string;
  order_id?: string;
  free_trial?: boolean;
  provisioned?: boolean;
  subscription_url?: string;
}

export interface AppConfig {
  brand_name: string;
  support_url: string;
  bot_username: string;
  months_labels: Record<string, string>;
  locale?: string;
  i18n?: Record<string, unknown>;
}

export interface I18nApiBundle {
  locale: string;
  rtl: boolean;
  cabinet?: Record<string, string>;
  locale_labels?: Record<string, string>;
  supported_locales?: string[];
}
