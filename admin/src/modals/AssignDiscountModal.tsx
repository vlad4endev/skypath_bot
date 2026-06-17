import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Modal } from '../components/ui';

const PLAN_OPTIONS = ['BASIC', 'MULTI', 'SUPER'];
const MONTH_OPTIONS = ['1', '2', '3', '6', '12'];

export interface AssignDiscountPrefill {
  discount_pct?: number | null;
  discount_amount?: number | null;
  plans?: string[] | null;
  months?: string[] | null;
  min_amount?: number | null;
  expires_at?: string | null;
  source_name?: string | null;
  promo_id?: number;
  promotion_id?: number;
}

interface AssignDiscountModalProps {
  open: boolean;
  onClose: () => void;
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
  userId?: number | null;
  telegramId?: number | null;
  userLabel?: string;
  prefill?: AssignDiscountPrefill | null;
}

export function AssignDiscountModal({
  open,
  onClose,
  onToast,
  userId,
  telegramId: initialTelegramId,
  userLabel,
  prefill,
}: AssignDiscountModalProps) {
  const [telegramId, setTelegramId] = useState('');
  const [discountPct, setDiscountPct] = useState('');
  const [discountAmount, setDiscountAmount] = useState('');
  const [selectedPlans, setSelectedPlans] = useState<string[]>([]);
  const [selectedMonths, setSelectedMonths] = useState<string[]>([]);
  const [minAmount, setMinAmount] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [message, setMessage] = useState('');
  const [code, setCode] = useState('');
  const [sendNotification, setSendNotification] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTelegramId(initialTelegramId ? String(initialTelegramId) : '');
    setDiscountPct(prefill?.discount_pct != null ? String(prefill.discount_pct) : '10');
    setDiscountAmount(prefill?.discount_amount != null ? String(prefill.discount_amount) : '');
    setSelectedPlans(prefill?.plans || []);
    setSelectedMonths((prefill?.months || []).map(String));
    setMinAmount(prefill?.min_amount != null ? String(prefill.min_amount) : '');
    setExpiresAt(prefill?.expires_at ? prefill.expires_at.slice(0, 10) : '');
    setMessage('');
    setCode('');
    setSendNotification(true);
  }, [open, initialTelegramId, prefill]);

  const togglePlan = (plan: string) => {
    setSelectedPlans((prev) =>
      prev.includes(plan) ? prev.filter((p) => p !== plan) : [...prev, plan],
    );
  };

  const toggleMonth = (month: string) => {
    setSelectedMonths((prev) =>
      prev.includes(month) ? prev.filter((m) => m !== month) : [...prev, month],
    );
  };

  const save = async () => {
    if (!discountPct && !discountAmount) {
      onToast('Укажите скидку в % или ₽', 'error');
      return;
    }
    if (!userId && !telegramId.trim()) {
      onToast('Укажите Telegram ID пользователя', 'error');
      return;
    }

    const body: Record<string, unknown> = {
      discount_pct: discountPct ? +discountPct : 0,
      discount_amount: discountAmount ? +discountAmount : 0,
      plans: selectedPlans.length ? selectedPlans : null,
      months: selectedMonths.length ? selectedMonths : null,
      min_amount: minAmount ? +minAmount : 0,
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
      message: message.trim() || null,
      code: code.trim().toUpperCase() || null,
      send_notification: sendNotification,
      source_name: prefill?.source_name || null,
    };
    if (prefill?.promo_id) body.promo_id = prefill.promo_id;
    if (prefill?.promotion_id) body.promotion_id = prefill.promotion_id;

    setSaving(true);
    try {
      let result: { code: string; notified?: boolean; warning?: string };
      if (userId) {
        result = await api.assignUserDiscount(userId, body);
      } else {
        body.telegram_id = +telegramId.trim();
        result = await api.assignDiscountByTelegram(body);
      }
      if (result.warning) {
        onToast(result.warning, 'info');
      } else {
        onToast(
          sendNotification
            ? `Скидка ${result.code} назначена и отправлена пользователю`
            : `Промокод ${result.code} создан`,
          'success',
        );
      }
      onClose();
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Ошибка', 'error');
    } finally {
      setSaving(false);
    }
  };

  const title = prefill?.source_name
    ? `Назначить: ${prefill.source_name}`
    : 'Назначить персональную скидку';

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={saving}>
            Отмена
          </button>
          <button type="button" className="btn btn--primary" onClick={save} disabled={saving}>
            {saving ? 'Отправка…' : sendNotification ? 'Назначить и отправить' : 'Создать промокод'}
          </button>
        </>
      }
    >
      {userLabel && (
        <p className="modal-desc">
          Пользователь: <strong>{userLabel}</strong>
        </p>
      )}
      {!userId && (
        <label className="field">
          <span>Telegram ID *</span>
          <input
            value={telegramId}
            onChange={(e) => setTelegramId(e.target.value.replace(/\D/g, ''))}
            placeholder="123456789"
          />
        </label>
      )}
      <div className="form-row">
        <label className="field">
          <span>Скидка %</span>
          <input type="number" min={0} max={100} value={discountPct} onChange={(e) => setDiscountPct(e.target.value)} />
        </label>
        <label className="field">
          <span>Скидка ₽</span>
          <input type="number" min={0} value={discountAmount} onChange={(e) => setDiscountAmount(e.target.value)} />
        </label>
      </div>
      <label className="field">
        <span>Свой код (необязательно)</span>
        <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="Авто VIP…" />
      </label>
      <label className="field">
        <span>Тарифы</span>
        <div className="checkbox-row" style={{ flexWrap: 'wrap', gap: 8 }}>
          {PLAN_OPTIONS.map((plan) => (
            <label key={plan} className="checkbox-row">
              <input type="checkbox" checked={selectedPlans.includes(plan)} onChange={() => togglePlan(plan)} />
              <span>{plan}</span>
            </label>
          ))}
        </div>
      </label>
      <label className="field">
        <span>Сроки, мес.</span>
        <div className="checkbox-row" style={{ flexWrap: 'wrap', gap: 8 }}>
          {MONTH_OPTIONS.map((month) => (
            <label key={month} className="checkbox-row">
              <input type="checkbox" checked={selectedMonths.includes(month)} onChange={() => toggleMonth(month)} />
              <span>{month}</span>
            </label>
          ))}
        </div>
      </label>
      <label className="field">
        <span>Действует до</span>
        <input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
      </label>
      <label className="field">
        <span>Сообщение пользователю</span>
        <textarea
          rows={3}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Например: спасибо за ожидание — держите персональную скидку!"
          style={{ width: '100%', resize: 'vertical' }}
        />
      </label>
      <label className="checkbox-row">
        <input type="checkbox" checked={sendNotification} onChange={(e) => setSendNotification(e.target.checked)} />
        <span>Отправить уведомление в Telegram</span>
      </label>
    </Modal>
  );
}
