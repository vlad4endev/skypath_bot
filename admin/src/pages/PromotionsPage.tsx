import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { api } from '../api/client';
import type { PromotionRow } from '../types';
import { Badge, Modal, Spinner } from '../components/ui';
import { fmtDate } from '../utils/format';
import { AssignDiscountModal, type AssignDiscountPrefill } from '../modals/AssignDiscountModal';

interface PromotionsPageProps {
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

const PLAN_OPTIONS = ['BASIC', 'MULTI', 'SUPER'];
const MONTH_OPTIONS = ['1', '2', '3', '6', '12'];

function formatRestrictions(plans: string[] | null, months: string[] | null) {
  const parts: string[] = [];
  if (plans?.length) parts.push(`тарифы: ${plans.join(', ')}`);
  if (months?.length) parts.push(`сроки: ${months.join(', ')} мес`);
  return parts.length ? parts.join(' · ') : 'Все тарифы и сроки';
}

function formatDiscount(row: PromotionRow) {
  if (row.discount_pct) return `${row.discount_pct}%`;
  if (row.discount_amount) return `${row.discount_amount}₽`;
  return '—';
}

export function PromotionsPage({ onToast }: PromotionsPageProps) {
  const [items, setItems] = useState<PromotionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [discountPct, setDiscountPct] = useState('');
  const [discountAmount, setDiscountAmount] = useState('');
  const [selectedPlans, setSelectedPlans] = useState<string[]>([]);
  const [selectedMonths, setSelectedMonths] = useState<string[]>([]);
  const [minAmount, setMinAmount] = useState('');
  const [newUsersOnly, setNewUsersOnly] = useState(false);
  const [startsAt, setStartsAt] = useState('');
  const [endsAt, setEndsAt] = useState('');
  const [priority, setPriority] = useState('0');
  const [stackable, setStackable] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const [assignPrefill, setAssignPrefill] = useState<AssignDiscountPrefill | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setItems(await api.promotions());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const resetForm = () => {
    setEditId(null);
    setName('');
    setDescription('');
    setDiscountPct('10');
    setDiscountAmount('');
    setSelectedPlans([]);
    setSelectedMonths([]);
    setMinAmount('');
    setNewUsersOnly(false);
    setStartsAt('');
    setEndsAt('');
    setPriority('0');
    setStackable(false);
    setIsActive(true);
  };

  const openCreate = () => {
    resetForm();
    setFormOpen(true);
  };

  const openEdit = (p: PromotionRow) => {
    setEditId(p.id);
    setName(p.name);
    setDescription(p.description || '');
    setDiscountPct(p.discount_pct != null ? String(p.discount_pct) : '');
    setDiscountAmount(p.discount_amount != null ? String(p.discount_amount) : '');
    setSelectedPlans(p.plans || []);
    setSelectedMonths((p.months || []).map(String));
    setMinAmount(p.min_amount != null ? String(p.min_amount) : '');
    setNewUsersOnly(p.new_users_only);
    setStartsAt(p.starts_at ? p.starts_at.slice(0, 16) : '');
    setEndsAt(p.ends_at ? p.ends_at.slice(0, 16) : '');
    setPriority(String(p.priority ?? 0));
    setStackable(p.stackable_with_promo);
    setIsActive(p.is_active);
    setFormOpen(true);
  };

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
    if (!name.trim()) {
      onToast('Укажите название акции', 'error');
      return;
    }
    const body: Record<string, unknown> = {
      name: name.trim(),
      description: description.trim() || null,
      discount_pct: discountPct ? +discountPct : 0,
      discount_amount: discountAmount ? +discountAmount : 0,
      plans: selectedPlans.length ? selectedPlans : null,
      months: selectedMonths.length ? selectedMonths : null,
      min_amount: minAmount ? +minAmount : 0,
      new_users_only: newUsersOnly,
      starts_at: startsAt ? new Date(startsAt).toISOString() : null,
      ends_at: endsAt ? new Date(endsAt).toISOString() : null,
      priority: priority ? +priority : 0,
      stackable_with_promo: stackable,
      is_active: isActive,
    };

    if (editId) {
      await api.updatePromotion(editId, body);
      onToast('Акция обновлена', 'success');
    } else {
      await api.createPromotion(body);
      onToast('Акция создана', 'success');
    }
    setFormOpen(false);
    load();
  };

  const remove = async (id: number) => {
    if (!confirm('Удалить акцию?')) return;
    await api.deletePromotion(id);
    onToast('Удалена', 'success');
    load();
  };

  const openAssign = (p: PromotionRow) => {
    setAssignPrefill({
      promotion_id: p.id,
      discount_pct: p.discount_pct,
      discount_amount: p.discount_amount,
      plans: p.plans,
      months: p.months,
      min_amount: p.min_amount,
      expires_at: p.ends_at,
      source_name: p.name,
    });
    setAssignOpen(true);
  };

  const statusBadge = (p: PromotionRow) => {
    if (!p.is_active) return <Badge variant="muted">ВЫКЛ</Badge>;
    if (p.is_valid) return <Badge variant="success">АКТИВНА</Badge>;
    return <Badge variant="danger">НЕ ДЕЙСТВУЕТ</Badge>;
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Акции</h1>
          <p className="page-desc">Автоматические скидки при оплате — без ввода кода</p>
        </div>
        <button type="button" className="btn btn--primary" onClick={openCreate}>
          <Plus size={18} /> Новая акция
        </button>
      </header>

      <div className="card table-card">
        {loading ? (
          <div className="page-loading"><Spinner /></div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Название</th>
                  <th>Скидка</th>
                  <th>Условия</th>
                  <th>Период</th>
                  <th>Статус</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr><td colSpan={6} className="empty-cell">Нет акций</td></tr>
                ) : (
                  items.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <strong>{p.name}</strong>
                        {p.description && (
                          <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
                            {p.description}
                          </div>
                        )}
                      </td>
                      <td>{formatDiscount(p)}</td>
                      <td style={{ fontSize: 13 }}>
                        {formatRestrictions(p.plans, p.months)}
                        {p.new_users_only && <div>Только новые пользователи</div>}
                        {p.stackable_with_promo && <div>Суммируется с промокодом</div>}
                      </td>
                      <td style={{ fontSize: 13 }}>
                        {p.starts_at ? fmtDate(p.starts_at) : 'сразу'}
                        {' — '}
                        {p.ends_at ? fmtDate(p.ends_at) : '∞'}
                      </td>
                      <td>{statusBadge(p)}</td>
                      <td className="actions">
                        <button type="button" className="btn btn--ghost btn--sm" onClick={() => openAssign(p)}>
                          🎁 Назначить
                        </button>
                        <button type="button" className="btn btn--ghost btn--sm" onClick={() => openEdit(p)}>
                          Изменить
                        </button>
                        <button type="button" className="btn btn--danger btn--sm" onClick={() => remove(p.id)}>✕</button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={editId ? 'Изменить акцию' : 'Новая акция'}
        footer={
          <>
            <button type="button" className="btn btn--ghost" onClick={() => setFormOpen(false)}>Отмена</button>
            <button type="button" className="btn btn--primary" onClick={save}>Сохранить</button>
          </>
        }
      >
        <label className="field">
          <span>Название *</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Летняя скидка 20%" />
        </label>
        <label className="field">
          <span>Описание</span>
          <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Показывается в расчёте скидки" />
        </label>
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
          <span>Тарифы (пусто = все)</span>
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
          <span>Сроки, мес. (пусто = все)</span>
          <div className="checkbox-row" style={{ flexWrap: 'wrap', gap: 8 }}>
            {MONTH_OPTIONS.map((month) => (
              <label key={month} className="checkbox-row">
                <input type="checkbox" checked={selectedMonths.includes(month)} onChange={() => toggleMonth(month)} />
                <span>{month}</span>
              </label>
            ))}
          </div>
        </label>
        <div className="form-row">
          <label className="field">
            <span>Мин. сумма заказа, ₽</span>
            <input type="number" min={0} value={minAmount} onChange={(e) => setMinAmount(e.target.value)} />
          </label>
          <label className="field">
            <span>Приоритет</span>
            <input type="number" value={priority} onChange={(e) => setPriority(e.target.value)} />
          </label>
        </div>
        <div className="form-row">
          <label className="field">
            <span>Начало</span>
            <input type="datetime-local" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
          </label>
          <label className="field">
            <span>Окончание</span>
            <input type="datetime-local" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
          </label>
        </div>
        <label className="checkbox-row">
          <input type="checkbox" checked={newUsersOnly} onChange={(e) => setNewUsersOnly(e.target.checked)} />
          <span>Только для новых пользователей</span>
        </label>
        <label className="checkbox-row">
          <input type="checkbox" checked={stackable} onChange={(e) => setStackable(e.target.checked)} />
          <span>Суммировать с промокодом</span>
        </label>
        <label className="checkbox-row">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
          <span>Активна</span>
        </label>
      </Modal>

      <AssignDiscountModal
        open={assignOpen}
        onClose={() => setAssignOpen(false)}
        onToast={onToast}
        prefill={assignPrefill}
      />
    </div>
  );
}
