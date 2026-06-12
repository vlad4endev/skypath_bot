import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { api } from '../api/client';
import type { PromoRow } from '../types';
import { Badge, Modal, Spinner } from '../components/ui';
import { fmtDate } from '../utils/format';
import { AssignDiscountModal, type AssignDiscountPrefill } from '../modals/AssignDiscountModal';

interface PromosPageProps {
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

const PLAN_OPTIONS = ['BASIC', 'MULTI', 'SUPER'];
const MONTH_OPTIONS = ['1', '3', '6', '12'];

export function PromosPage({ onToast }: PromosPageProps) {
  const [items, setItems] = useState<PromoRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);

  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [discountPct, setDiscountPct] = useState('');
  const [discountAmount, setDiscountAmount] = useState('');
  const [selectedPlans, setSelectedPlans] = useState<string[]>([]);
  const [selectedMonths, setSelectedMonths] = useState<string[]>([]);
  const [minAmount, setMinAmount] = useState('');
  const [maxUses, setMaxUses] = useState('');
  const [onePerUser, setOnePerUser] = useState(true);
  const [isActive, setIsActive] = useState(true);
  const [expiresAt, setExpiresAt] = useState('');
  const [assignPrefill, setAssignPrefill] = useState<AssignDiscountPrefill | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setItems(await api.promos());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const resetForm = () => {
    setEditId(null);
    setCode('');
    setName('');
    setDescription('');
    setDiscountPct('10');
    setDiscountAmount('');
    setSelectedPlans([]);
    setSelectedMonths([]);
    setMinAmount('');
    setMaxUses('100');
    setOnePerUser(true);
    setIsActive(true);
    setExpiresAt('');
  };

  const openCreate = () => {
    resetForm();
    setFormOpen(true);
  };

  const openEdit = (p: PromoRow) => {
    setEditId(p.id);
    setCode(p.code);
    setName(p.name || '');
    setDescription(p.description || '');
    setDiscountPct(p.discount_pct != null ? String(p.discount_pct) : '');
    setDiscountAmount(p.discount_amount != null ? String(p.discount_amount) : '');
    setSelectedPlans(p.plans || []);
    setSelectedMonths((p.months || []).map(String));
    setMinAmount(p.min_amount != null ? String(p.min_amount) : '');
    setMaxUses(p.max_uses != null ? String(p.max_uses) : '');
    setOnePerUser(p.one_per_user);
    setIsActive(p.is_active);
    setExpiresAt(p.expires_at ? p.expires_at.slice(0, 10) : '');
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
    if (!code.trim()) {
      onToast('Укажите код промо', 'error');
      return;
    }
    const body: Record<string, unknown> = {
      code: code.trim().toUpperCase(),
      name: name.trim() || null,
      description: description.trim() || null,
      is_active: isActive,
      max_uses: maxUses ? +maxUses : null,
      min_amount: minAmount ? +minAmount : 0,
      one_per_user: onePerUser,
      plans: selectedPlans.length ? selectedPlans : null,
      months: selectedMonths.length ? selectedMonths : null,
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
    };
    if (discountPct) body.discount_pct = +discountPct;
    if (discountAmount) body.discount_amount = +discountAmount;

    if (editId) {
      await api.updatePromo(editId, body);
      onToast('Промокод обновлён', 'success');
    } else {
      await api.createPromo(body);
      onToast('Промокод создан', 'success');
    }
    setFormOpen(false);
    load();
  };

  const remove = async (id: number) => {
    if (!confirm('Удалить промокод?')) return;
    await api.deletePromo(id);
    onToast('Удалён', 'success');
    load();
  };

  const openAssign = (p: PromoRow) => {
    setAssignPrefill({
      promo_id: p.id,
      discount_pct: p.discount_pct,
      discount_amount: p.discount_amount,
      plans: p.plans,
      months: p.months,
      min_amount: p.min_amount,
      expires_at: p.expires_at,
      source_name: p.name || p.code,
    });
    setAssignOpen(true);
  };

  const statusBadge = (p: PromoRow) => {
    if (!p.is_active) return <Badge variant="muted">ВЫКЛ</Badge>;
    if (p.is_valid) return <Badge variant="success">АКТИВЕН</Badge>;
    return <Badge variant="danger">ИСТЁК</Badge>;
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Промокоды</h1>
          <p className="page-desc">Коды, которые пользователь вводит при оплате</p>
        </div>
        <button type="button" className="btn btn--primary" onClick={openCreate}>
          <Plus size={18} /> Новый промокод
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
                  <th>Код</th>
                  <th>Скидка</th>
                  <th>Ограничения</th>
                  <th>Использовано</th>
                  <th>Статус</th>
                  <th>До</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr><td colSpan={7} className="empty-cell">Нет промокодов</td></tr>
                ) : (
                  items.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <strong>{p.code}</strong>
                        {p.name && <div className="text-muted" style={{ fontSize: 12 }}>{p.name}</div>}
                      </td>
                      <td>{p.discount_pct ? `${p.discount_pct}%` : `${p.discount_amount}₽`}</td>
                      <td style={{ fontSize: 13 }}>
                        {p.plans?.length ? p.plans.join(', ') : 'все тарифы'}
                        {p.months?.length ? ` · ${p.months.join(', ')} мес` : ''}
                        {p.one_per_user ? ' · 1 раз/юзер' : ''}
                      </td>
                      <td>{p.uses_count} / {p.max_uses ?? '∞'}</td>
                      <td>{statusBadge(p)}</td>
                      <td>{fmtDate(p.expires_at) === '—' ? '∞' : fmtDate(p.expires_at)}</td>
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
        title={editId ? 'Изменить промокод' : 'Новый промокод'}
        footer={
          <>
            <button type="button" className="btn btn--ghost" onClick={() => setFormOpen(false)}>Отмена</button>
            <button type="button" className="btn btn--primary" onClick={save}>Сохранить</button>
          </>
        }
      >
        <label className="field">
          <span>Код *</span>
          <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="SKY10" disabled={!!editId} />
        </label>
        <label className="field">
          <span>Название</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Скидка 10% для друзей" />
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
        <div className="form-row">
          <label className="field">
            <span>Макс. использований</span>
            <input type="number" min={1} value={maxUses} onChange={(e) => setMaxUses(e.target.value)} />
          </label>
          <label className="field">
            <span>Мин. сумма, ₽</span>
            <input type="number" min={0} value={minAmount} onChange={(e) => setMinAmount(e.target.value)} />
          </label>
        </div>
        <label className="field">
          <span>Действует до</span>
          <input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
        </label>
        <label className="checkbox-row">
          <input type="checkbox" checked={onePerUser} onChange={(e) => setOnePerUser(e.target.checked)} />
          <span>Один раз на пользователя</span>
        </label>
        <label className="checkbox-row">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
          <span>Активен</span>
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
