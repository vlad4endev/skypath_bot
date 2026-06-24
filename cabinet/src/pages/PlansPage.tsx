import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, Sparkles, Tag } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { DashboardData, PlanInfo } from '../types';
import { Spinner } from '../components/ui';

const PLAN_ORDER = ['FREE', 'BASIC', 'MULTI', 'SUPER'];

export function PlansPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
  const [selectedMonths, setSelectedMonths] = useState(1);
  const [promoCode, setPromoCode] = useState('');
  const [promoLabel, setPromoLabel] = useState('');
  const [promoError, setPromoError] = useState('');
  const [discounts, setDiscounts] = useState<Record<number, number>>({});
  const [paying, setPaying] = useState(false);
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const dash = await api.dashboard();
      setData(dash);
      if (dash.plans && !selectedPlan) {
        const keys = PLAN_ORDER.filter((k) => dash.plans?.[k]);
        setSelectedPlan(keys.find((k) => k === 'MULTI') || keys[0] || null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, [selectedPlan]);

  useEffect(() => {
    load();
  }, [load]);

  const plans = data?.plans ?? {};
  const plan: PlanInfo | null = selectedPlan ? plans[selectedPlan] ?? null : null;
  const canRenew = data?.can_renew ?? !data?.has_subscription;
  const plansLocked = Boolean(data?.has_subscription && !canRenew);
  const monthsLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    if (plan?.prices) {
      Object.keys(plan.prices).forEach((m) => {
        labels[m] = `${m} мес.`;
      });
    }
    return labels;
  }, [plan]);

  const loadDiscounts = useCallback(async (planKey: string) => {
    try {
      const res = await api.previewDiscount(planKey);
      const map: Record<number, number> = {};
      const months = (res as { months?: Record<string, { final_price: number }> }).months || {};
      for (const [m, preview] of Object.entries(months)) {
        map[Number(m)] = preview.final_price;
      }
      setDiscounts(map);
    } catch {
      setDiscounts({});
    }
  }, []);

  useEffect(() => {
    if (selectedPlan && plans[selectedPlan]?.prices) {
      loadDiscounts(selectedPlan);
    }
  }, [selectedPlan, plans, loadDiscounts]);

  const basePrice = plan?.prices?.[String(selectedMonths)] ?? 0;
  const finalPrice = discounts[selectedMonths] ?? basePrice;

  const showToast = (msg: string, isError = false) => {
    setToast(isError ? `❌ ${msg}` : msg);
    setTimeout(() => setToast(''), 3000);
  };

  const applyPromo = async () => {
    if (!selectedPlan || !promoCode.trim()) return;
    setPromoError('');
    try {
      const res = await api.validatePromo(selectedPlan, selectedMonths, promoCode.trim());
      if (res.valid) {
        setPromoLabel(res.discount_label || `−${res.discount_total} ₽`);
        if (res.final_price != null) {
          setDiscounts((prev) => ({ ...prev, [selectedMonths]: res.final_price! }));
        }
      }
    } catch (e) {
      setPromoError(e instanceof ApiError ? e.message : 'Промокод недействителен');
      setPromoLabel('');
    }
  };

  const handlePay = async () => {
    if (!selectedPlan || !plan) return;
    setPaying(true);
    try {
      const result = await api.pay({
        plan: selectedPlan,
        months: selectedMonths,
        price: finalPrice,
        promo_code: promoCode.trim() || undefined,
      });

      if (result.error) {
        showToast(result.message || result.error, true);
        return;
      }

      if (result.provisioned && result.subscription_url) {
        showToast('✅ Подписка активирована!');
        await load();
        return;
      }

      if (result.free_trial) {
        showToast(result.message || '✅ Пробный период активирован');
        await load();
        return;
      }

      if (result.payment_url) {
        if (result.order_id) {
          sessionStorage.setItem('pending_order_id', result.order_id);
        }
        window.location.href = result.payment_url;
        return;
      }

      showToast('Неожиданный ответ сервера', true);
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Ошибка оплаты', true);
    } finally {
      setPaying(false);
    }
  };

  if (loading) {
    return (
      <div className="page-loading">
        <Spinner size={32} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="page-error">
        <p>{error || 'Ошибка'}</p>
      </div>
    );
  }

  const showPlansBlocked = plansLocked;

  return (
    <div className="page plans-page">
      <header className="page-header">
        <h1>{canRenew && data.has_subscription ? 'Продление' : 'Тарифы'}</h1>
        <p className="subtitle">
          {canRenew && data.has_subscription
            ? 'Выберите срок продления подписки'
            : 'Выберите подходящий план'}
        </p>
      </header>

      {toast && <div className="inline-toast">{toast}</div>}

      {data.has_subscription && (
        <section className="card">
          <p>Текущий тариф: <strong>{data.subscription?.plan_name}</strong></p>
          {canRenew && data.subscription && (
            <p className="hint">
              {data.subscription.is_active
                ? `Подписка активна ещё ${data.subscription.days_left} дн. — можно продлить сейчас.`
                : 'Подписка истекла — выберите тариф для продления.'}
            </p>
          )}
        </section>
      )}

      {showPlansBlocked ? (
        <section className="card">
          <p>Тарифы недоступны при активной подписке. Обратитесь в поддержку для продления.</p>
        </section>
      ) : !Object.keys(plans).length ? (
        <section className="card">
          <p>Тарифы временно недоступны. Попробуйте обновить страницу или обратитесь в поддержку.</p>
        </section>
      ) : !selectedPlan ? (
        <div className="plans-grid">
          {PLAN_ORDER.filter((k) => plans[k]).map((key) => {
            const p = plans[key];
            const priceLabel = p.price === 0
              ? 'Бесплатно'
              : p.prices
                ? `от ${Math.min(...Object.values(p.prices))} ₽`
                : '';
            return (
              <button
                key={key}
                type="button"
                className={`plan-card ${p.recommended ? 'recommended' : ''}`}
                onClick={() => setSelectedPlan(key)}
              >
                {p.recommended && (
                  <span className="plan-badge"><Sparkles size={14} /> Рекомендуем</span>
                )}
                <h3>{p.name}</h3>
                <p className="plan-desc">{p.description}</p>
                <ul className="plan-features">
                  {p.features.map((f) => (
                    <li key={f}><Check size={16} /> {f}</li>
                  ))}
                </ul>
                <div className="plan-price">{priceLabel}</div>
              </button>
            );
          })}
        </div>
      ) : plan && (
        <section className="card plan-detail">
          <button type="button" className="back-link" onClick={() => setSelectedPlan(null)}>
            ← Все тарифы
          </button>

          <h2>{plan.name}</h2>
          <p className="plan-desc">{plan.description}</p>

          <ul className="plan-features">
            {plan.features.map((f) => (
              <li key={f}><Check size={16} /> {f}</li>
            ))}
          </ul>

          {plan.key === 'FREE' ? (
            <div className="checkout">
              <p className="price-big">Бесплатно · {plan.days} дня</p>
              <button type="button" className="btn btn--primary btn--block" onClick={handlePay} disabled={paying}>
                {paying ? 'Активация…' : 'Активировать пробный период'}
              </button>
            </div>
          ) : plan.prices && (
            <div className="checkout">
              <div className="months-picker">
                {Object.entries(plan.prices).map(([m, base]) => {
                  const months = Number(m);
                  const price = discounts[months] ?? base;
                  return (
                    <button
                      key={m}
                      type="button"
                      className={`month-btn ${selectedMonths === months ? 'selected' : ''}`}
                      onClick={() => {
                        setSelectedMonths(months);
                        setPromoLabel('');
                        setPromoError('');
                      }}
                    >
                      <span>{monthsLabels[m] || `${m} мес.`}</span>
                      <strong>{price} ₽</strong>
                      {price < base && <em>−{base - price} ₽</em>}
                    </button>
                  );
                })}
              </div>

              <div className="promo-row">
                <div className="input-wrap flex-1">
                  <Tag size={18} className="input-icon" />
                  <input
                    type="text"
                    placeholder="Промокод"
                    value={promoCode}
                    onChange={(e) => setPromoCode(e.target.value.toUpperCase())}
                  />
                </div>
                <button type="button" className="btn btn--secondary" onClick={applyPromo}>
                  Применить
                </button>
              </div>
              {promoError && <p className="form-error">{promoError}</p>}
              {promoLabel && <p className="promo-ok">{promoLabel}</p>}

              <div className="checkout-total">
                {finalPrice < basePrice && (
                  <span className="old-price">{basePrice} ₽</span>
                )}
                <span className="price-big">{finalPrice} ₽</span>
              </div>

              <button type="button" className="btn btn--primary btn--block" onClick={handlePay} disabled={paying}>
                {paying ? 'Оформление…' : canRenew && data.has_subscription ? `Продлить за ${finalPrice} ₽` : `Оплатить ${finalPrice} ₽`}
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
