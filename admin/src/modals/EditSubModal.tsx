import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useConfig } from '../hooks/useConfig';
import type { SubscriptionRow } from '../types';
import { Modal, Spinner } from '../components/ui';
import { toDatetimeLocal } from '../utils/format';

interface EditSubModalProps {
  subId: number | null;
  onClose: () => void;
  onSaved: () => void;
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

export function EditSubModal({ subId, onClose, onSaved, onToast }: EditSubModalProps) {
  const { config } = useConfig();
  const [sub, setSub] = useState<SubscriptionRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [xuiMsg, setXuiMsg] = useState('');

  const [plan, setPlan] = useState('');
  const [status, setStatus] = useState('');
  const [expires, setExpires] = useState('');
  const [addDays, setAddDays] = useState('');
  const [addMonths, setAddMonths] = useState('');
  const [limitIp, setLimitIp] = useState(3);

  useEffect(() => {
    if (!subId) return;
    setLoading(true);
    setError('');
    setXuiMsg('');
    api
      .subscription(subId)
      .then((s) => {
        setSub(s);
        setPlan(s.plan);
        setStatus(s.status);
        setExpires(toDatetimeLocal(s.expires_at));
        setLimitIp(s.limit_ip);
        setAddDays('');
        setAddMonths('');
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Ошибка'))
      .finally(() => setLoading(false));
  }, [subId]);

  const save = async () => {
    if (!subId) return;
    setSaving(true);
    setError('');
    setXuiMsg('');
    try {
      const body: Record<string, unknown> = { plan, status, limit_ip: limitIp };
      if (expires) body.expires_at = new Date(expires).toISOString();
      if (addDays) body.extend_days = +addDays;
      if (addMonths) body.extend_months = +addMonths;

      const res = await api.updateSubscription(subId, body);
      const xui = res.xui_sync;
      if (xui) {
        setXuiMsg(xui.message || (xui.ok ? '3X-UI: OK' : '3X-UI: ошибка'));
        if (!xui.ok && !xui.skipped) {
          setError('БД обновлена, но 3X-UI: ' + (xui.message || 'ошибка'));
          return;
        }
      }
      onToast('Подписка сохранена', 'success');
      onClose();
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const disableVpn = async () => {
    if (!subId) return;
    if (!confirm('Отключить VPN у клиента в 3X-UI и заблокировать подписку?')) return;
    setSaving(true);
    try {
      const res = await api.updateSubscription(subId, { disable: true });
      setXuiMsg(res.xui_sync?.message || 'VPN отключён');
      onToast('VPN отключён', 'success');
      setTimeout(() => {
        onClose();
        onSaved();
      }, 800);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setSaving(false);
    }
  };

  const hasVpn = !!(sub?.vpn_uuid && sub?.vpn_email);

  return (
    <Modal
      open={subId !== null}
      onClose={onClose}
      title={sub ? `Подписка #${sub.id}` : 'Подписка'}
      footer={
        sub && (
          <>
            <button type="button" className="btn btn--ghost" onClick={onClose}>
              Отмена
            </button>
            <button type="button" className="btn btn--danger btn--sm" onClick={disableVpn} disabled={saving}>
              Отключить VPN
            </button>
            <button type="button" className="btn btn--primary" onClick={save} disabled={saving}>
              {saving ? 'Сохранение…' : 'Сохранить → 3X-UI'}
            </button>
          </>
        )
      }
    >
      {loading && <Spinner />}
      {!loading && sub && (
        <>
          <p className="banner banner--info">
            Изменения сохраняются в БД и отправляются в <b>3X-UI</b>
            {hasVpn ? ` (клиент: ${sub.vpn_email})` : ' — VPN-клиент не создан'}
          </p>
          <div className="detail-grid">
            <div className="detail-item"><label>Telegram</label><span className="mono">{sub.telegram_id}</span></div>
            <div className="detail-item"><label>Осталось</label><span>{sub.is_active ? `${sub.days_left} дн.` : '—'}</span></div>
            <div className="detail-item"><label>Sub ID</label><span className="mono truncate">{sub.vpn_sub_id || '—'}</span></div>
            <div className="detail-item"><label>Inbound</label><span>{sub.inbound_id ?? '—'}</span></div>
          </div>
          <div className="form-row">
            <label className="field">
              <span>План</span>
              <select value={plan} onChange={(e) => setPlan(e.target.value)}>
                {(config?.plan_types || [sub.plan]).map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Статус</span>
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                {(config?.subscription_statuses || [sub.status]).map((st) => (
                  <option key={st} value={st}>{st}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="field">
            <span>Окончание (точная дата)</span>
            <input type="datetime-local" value={expires} onChange={(e) => setExpires(e.target.value)} />
          </label>
          <div className="form-row">
            <label className="field">
              <span>+ дней</span>
              <input type="number" min={0} value={addDays} onChange={(e) => setAddDays(e.target.value)} placeholder="0" />
            </label>
            <label className="field">
              <span>+ месяцев</span>
              <input type="number" min={0} value={addMonths} onChange={(e) => setAddMonths(e.target.value)} placeholder="0" />
            </label>
          </div>
          <div className="quick-actions">
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setAddDays('7')}>+7 дней</button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setAddDays('30')}>+30 дней</button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setAddMonths('1')}>+1 мес</button>
            <button type="button" className="btn btn--success btn--sm" onClick={() => setStatus('АКТИВНА')}>Включить</button>
            <button type="button" className="btn btn--danger btn--sm" onClick={() => setStatus('ЗАБЛОКИРОВАНА')}>Отключить</button>
          </div>
          <label className="field">
            <span>Устройств (limitIp)</span>
            <input type="number" min={1} value={limitIp} onChange={(e) => setLimitIp(+e.target.value)} />
          </label>
          {error && <p className="form-error">{error}</p>}
          {xuiMsg && <p className="banner banner--success">{xuiMsg}</p>}
        </>
      )}
    </Modal>
  );
}
