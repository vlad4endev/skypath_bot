import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { api } from '../api/client';
import type { PromoRow } from '../types';
import { Badge, Modal, Spinner } from '../components/ui';
import { fmtDate } from '../utils/format';

interface PromosPageProps {
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

export function PromosPage({ onToast }: PromosPageProps) {
  const [items, setItems] = useState<PromoRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);

  const [code, setCode] = useState('');
  const [discountPct, setDiscountPct] = useState('');
  const [discountAmount, setDiscountAmount] = useState('');
  const [maxUses, setMaxUses] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [expiresAt, setExpiresAt] = useState('');

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

  const openCreate = () => {
    setEditId(null);
    setCode('');
    setDiscountPct('10');
    setDiscountAmount('');
    setMaxUses('100');
    setIsActive(true);
    setExpiresAt('');
    setFormOpen(true);
  };

  const openEdit = (p: PromoRow) => {
    setEditId(p.id);
    setCode(p.code);
    setDiscountPct(p.discount_pct != null ? String(p.discount_pct) : '');
    setDiscountAmount(p.discount_amount != null ? String(p.discount_amount) : '');
    setMaxUses(p.max_uses != null ? String(p.max_uses) : '');
    setIsActive(p.is_active);
    setExpiresAt(p.expires_at ? p.expires_at.slice(0, 10) : '');
    setFormOpen(true);
  };

  const save = async () => {
    if (!code.trim()) {
      onToast('Укажите код промо', 'error');
      return;
    }
    const body: Record<string, unknown> = {
      code: code.trim().toUpperCase(),
      is_active: isActive,
      max_uses: maxUses ? +maxUses : null,
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

  const statusBadge = (p: PromoRow) => {
    if (!p.is_active) return <Badge variant="muted">ВЫКЛ</Badge>;
    if (p.is_valid) return <Badge variant="success">АКТИВНА</Badge>;
    return <Badge variant="danger">ИСТЁК</Badge>;
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Промокоды</h1>
          <p className="page-desc">Скидки и лимиты использования</p>
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
                  <th>Использовано</th>
                  <th>Статус</th>
                  <th>До</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr><td colSpan={6} className="empty-cell">Нет промокодов</td></tr>
                ) : (
                  items.map((p) => (
                    <tr key={p.id}>
                      <td><strong>{p.code}</strong></td>
                      <td>{p.discount_pct ? `${p.discount_pct}%` : `${p.discount_amount}₽`}</td>
                      <td>{p.uses_count} / {p.max_uses ?? '∞'}</td>
                      <td>{statusBadge(p)}</td>
                      <td>{fmtDate(p.expires_at) === '—' ? '∞' : fmtDate(p.expires_at)}</td>
                      <td className="actions">
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
          <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="SKY10" />
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
          <span>Макс. использований</span>
          <input type="number" min={1} value={maxUses} onChange={(e) => setMaxUses(e.target.value)} />
        </label>
        <label className="field">
          <span>Действует до</span>
          <input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
        </label>
        <label className="checkbox-row">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
          <span>Активен</span>
        </label>
      </Modal>
    </div>
  );
}
