import { useCallback, useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { api } from '../api/client';
import type { PaymentRow } from '../types';
import { Badge, Modal, Pagination, Spinner } from '../components/ui';
import { fmtDate, fmtMoney, pagesCount } from '../utils/format';
import { useConfig } from '../hooks/useConfig';

interface PaymentsPageProps {
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

export function PaymentsPage({ onToast }: PaymentsPageProps) {
  const { config } = useConfig();
  const [items, setItems] = useState<PaymentRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [perPage] = useState(20);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [unfulfilled, setUnfulfilled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detail, setDetail] = useState<PaymentRow | null>(null);

  const load = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const data = await api.payments(p, search, status, unfulfilled);
      setItems(data.items);
      setTotal(data.total);
      setPage(data.page);
    } finally {
      setLoading(false);
    }
  }, [page, search, status, unfulfilled]);

  useEffect(() => {
    load(1);
  }, [search, status, unfulfilled]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load(page);
  }, [page]); // eslint-disable-line react-hooks/exhaustive-deps

  const openDetail = async (id: number) => {
    setDetailId(id);
    const p = await api.paymentDetail(id);
    setDetail(p);
  };

  const fulfill = async (id: number) => {
    if (!confirm('Выдать VPN-ключ для этого платежа?')) return;
    try {
      const r = await api.fulfillPayment(id);
      onToast(r.ok ? 'VPN ключ выдан' : 'Не удалось выдать ключ', r.ok ? 'success' : 'error');
      setDetailId(null);
      load(page);
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Ошибка', 'error');
    }
  };

  const remove = async (id: number) => {
    if (!confirm('Удалить платёж?')) return;
    await api.deletePayment(id);
    onToast('Платёж удалён', 'success');
    load(page);
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Платежи</h1>
          <p className="page-desc">История оплат и выдача VPN-ключей</p>
        </div>
        <div className="page-toolbar">
          <div className="search-wrap">
            <Search size={18} />
            <input
              type="search"
              placeholder="Order ID, telegram…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="select-filter">
            <option value="">Все статусы</option>
            {(config?.payment_statuses || []).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <label className="checkbox-inline">
            <input type="checkbox" checked={unfulfilled} onChange={(e) => setUnfulfilled(e.target.checked)} />
            Без VPN-ключа
          </label>
        </div>
      </header>

      <div className="card table-card">
        {loading ? (
          <div className="page-loading"><Spinner /></div>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Order</th>
                    <th>Telegram</th>
                    <th>Сумма</th>
                    <th>План</th>
                    <th>Статус</th>
                    <th>VPN</th>
                    <th>Дата</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {items.length === 0 ? (
                    <tr><td colSpan={9} className="empty-cell">Нет платежей</td></tr>
                  ) : (
                    items.map((p) => (
                      <tr key={p.id}>
                        <td>{p.id}</td>
                        <td className="mono truncate" title={p.order_id || ''}>{p.order_id?.slice(0, 12) || '—'}</td>
                        <td className="mono">{p.telegram_id || '—'}</td>
                        <td>{fmtMoney(p.paid_amount || p.amount)}</td>
                        <td>{p.plan ? `${p.plan}/${p.months}м` : '—'}</td>
                        <td><Badge variant={p.status === 'succeeded' ? 'success' : 'muted'}>{p.status}</Badge></td>
                        <td>{p.is_fulfilled ? '🔑' : p.status === 'succeeded' ? '⚠️' : '—'}</td>
                        <td>{fmtDate(p.paid_at || p.created_at)}</td>
                        <td className="actions">
                          {p.status === 'succeeded' && !p.is_fulfilled && (
                            <button type="button" className="btn btn--success btn--sm" onClick={() => fulfill(p.id)}>
                              VPN
                            </button>
                          )}
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => openDetail(p.id)}>
                            Детали
                          </button>
                          <button type="button" className="btn btn--danger btn--sm" onClick={() => remove(p.id)}>✕</button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pages={pagesCount(total, perPage)} onPage={setPage} />
          </>
        )}
      </div>

      <Modal
        open={detailId !== null && detail !== null}
        onClose={() => { setDetailId(null); setDetail(null); }}
        title={detail ? `Платёж #${detail.id}` : 'Платёж'}
        footer={
          detail && (
            <>
              <button type="button" className="btn btn--ghost" onClick={() => { setDetailId(null); setDetail(null); }}>
                Закрыть
              </button>
              {detail.status === 'succeeded' && !detail.is_fulfilled && (
                <button type="button" className="btn btn--success" onClick={() => fulfill(detail.id)}>
                  Выдать VPN
                </button>
              )}
            </>
          )
        }
      >
        {detail && (
          <>
            <div className="detail-grid">
              <div className="detail-item"><label>Order ID</label><span className="mono">{detail.order_id || '—'}</span></div>
              <div className="detail-item"><label>Provider ID</label><span className="mono">{detail.yookassa_id || '—'}</span></div>
              <div className="detail-item">
                <label>Сумма</label>
                <span>{fmtMoney(detail.amount)} → {detail.paid_amount ? fmtMoney(detail.paid_amount) : '—'}</span>
              </div>
              <div className="detail-item"><label>Статус</label><span>{detail.status} {detail.provider_status || ''}</span></div>
              <div className="detail-item"><label>План</label><span>{detail.plan}/{detail.months} мес</span></div>
              <div className="detail-item"><label>Telegram</label><span className="mono">{detail.telegram_id || '—'}</span></div>
              <div className="detail-item"><label>Создан</label><span>{fmtDate(detail.created_at)}</span></div>
              <div className="detail-item"><label>Оплачен</label><span>{fmtDate(detail.paid_at)}</span></div>
              <div className="detail-item"><label>VPN выдан</label><span>{fmtDate(detail.fulfilled_at) || '❌ Нет'}</span></div>
              <div className="detail-item"><label>Промокод</label><span>{detail.promo_code || '—'}</span></div>
            </div>
            {detail.payment_url && (
              <label className="field">
                <span>Ссылка оплаты</span>
                <input readOnly value={detail.payment_url} onClick={(e) => (e.target as HTMLInputElement).select()} />
              </label>
            )}
          </>
        )}
      </Modal>
    </div>
  );
}
