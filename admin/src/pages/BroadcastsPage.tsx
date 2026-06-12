import { useCallback, useEffect, useState } from 'react';
import { Plus, Send, Clock, XCircle, Trash2, Eye } from 'lucide-react';
import { api } from '../api/client';
import type { BroadcastRow, BroadcastTarget } from '../types';
import { Badge, Modal, Spinner } from '../components/ui';
import { fmtDate } from '../utils/format';

interface BroadcastsPageProps {
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

type FilterStatus = '' | 'scheduled' | 'sent' | 'failed';

const STATUS_LABELS: Record<string, string> = {
  scheduled: 'Запланирована',
  sending: 'Отправляется',
  sent: 'Отправлена',
  cancelled: 'Отменена',
  failed: 'Ошибка',
};

function statusVariant(status: string): 'success' | 'warning' | 'danger' | 'muted' | 'default' {
  if (status === 'sent') return 'success';
  if (status === 'scheduled' || status === 'sending') return 'warning';
  if (status === 'failed') return 'danger';
  if (status === 'cancelled') return 'muted';
  return 'default';
}

export function BroadcastsPage({ onToast }: BroadcastsPageProps) {
  const [items, setItems] = useState<BroadcastRow[]>([]);
  const [targets, setTargets] = useState<BroadcastTarget[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterStatus>('');
  const [formOpen, setFormOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewItem, setPreviewItem] = useState<BroadcastRow | null>(null);
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState('');
  const [text, setText] = useState('');
  const [target, setTarget] = useState('all');
  const [sendMode, setSendMode] = useState<'now' | 'scheduled'>('now');
  const [sendAt, setSendAt] = useState('');
  const [recipientCount, setRecipientCount] = useState<number | null>(null);
  const [countLoading, setCountLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setItems(await api.broadcasts(filter || undefined));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [filter]);

  useEffect(() => {
    api.broadcastTargets().then(setTargets).catch(() => {});
  }, []);

  const loadRecipientCount = useCallback(async (t: string) => {
    setCountLoading(true);
    try {
      const res = await api.broadcastEstimate(t);
      setRecipientCount(res.count);
    } catch {
      setRecipientCount(null);
    } finally {
      setCountLoading(false);
    }
  }, []);

  useEffect(() => {
    if (formOpen) {
      loadRecipientCount(target);
    }
  }, [formOpen, target, loadRecipientCount]);

  const resetForm = () => {
    setName('');
    setText('');
    setTarget('all');
    setSendMode('now');
    setSendAt('');
    setRecipientCount(null);
  };

  const openCreate = () => {
    resetForm();
    setFormOpen(true);
  };

  const save = async () => {
    if (!text.trim()) {
      onToast('Введите текст сообщения', 'error');
      return;
    }
    if (sendMode === 'scheduled' && !sendAt) {
      onToast('Укажите дату и время отправки', 'error');
      return;
    }
    setSaving(true);
    try {
      await api.createBroadcast({
        name: name.trim() || undefined,
        text: text.trim(),
        target,
        send_mode: sendMode,
        send_at: sendMode === 'scheduled' ? sendAt : undefined,
      });
      onToast(
        sendMode === 'now' ? 'Рассылка запущена' : 'Рассылка запланирована',
        'success',
      );
      setFormOpen(false);
      await load();
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Ошибка создания', 'error');
    } finally {
      setSaving(false);
    }
  };

  const sendNow = async (id: number) => {
    try {
      await api.sendBroadcastNow(id);
      onToast('Рассылка запущена', 'success');
      await load();
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Ошибка', 'error');
    }
  };

  const cancel = async (id: number) => {
    if (!confirm('Отменить запланированную рассылку?')) return;
    try {
      await api.cancelBroadcast(id);
      onToast('Рассылка отменена', 'info');
      await load();
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Ошибка', 'error');
    }
  };

  const remove = async (id: number) => {
    if (!confirm('Удалить рассылку из истории?')) return;
    try {
      await api.deleteBroadcast(id);
      onToast('Удалено', 'info');
      await load();
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Ошибка', 'error');
    }
  };

  const filters: { id: FilterStatus; label: string }[] = [
    { id: '', label: 'Все' },
    { id: 'scheduled', label: 'Запланированные' },
    { id: 'sent', label: 'Отправленные' },
    { id: 'failed', label: 'С ошибкой' },
  ];

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Рассылки</h1>
          <p className="page-desc">
            Массовые сообщения в Telegram — сразу или по расписанию
          </p>
        </div>
        <button type="button" className="btn btn--primary" onClick={openCreate}>
          <Plus size={18} />
          Новая рассылка
        </button>
      </header>

      <div className="page-toolbar" style={{ marginBottom: 0 }}>
        {filters.map((f) => (
          <button
            key={f.id}
            type="button"
            className={`btn btn--sm ${filter === f.id ? 'btn--primary' : 'btn--ghost'}`}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="card table-card">
      {loading ? (
        <div className="page-loading">
          <Spinner />
        </div>
      ) : items.length === 0 ? (
        <div className="empty-cell" style={{ padding: 32, textAlign: 'center' }}>
          <p>Рассылок пока нет</p>
          <button type="button" className="btn btn--primary" onClick={openCreate} style={{ marginTop: 12 }}>
            Создать первую
          </button>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Название</th>
                <th>Аудитория</th>
                <th>Статус</th>
                <th>Доставка</th>
                <th>Время</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((b) => (
                <tr key={b.id}>
                  <td>
                    <div>{b.name || `Рассылка #${b.id}`}</div>
                    <div className="text-muted" style={{ fontSize: 12, marginTop: 4, maxWidth: 220 }}>
                      {b.text.replace(/<[^>]+>/g, '').slice(0, 60)}
                      {b.text.length > 60 ? '…' : ''}
                    </div>
                  </td>
                  <td>
                    <div>{b.target_label}</div>
                    {b.target_count != null && (
                      <div className="text-muted" style={{ fontSize: 12 }}>~{b.target_count} чел.</div>
                    )}
                  </td>
                  <td>
                    <Badge variant={statusVariant(b.status)}>
                      {STATUS_LABELS[b.status] || b.status}
                    </Badge>
                  </td>
                  <td>
                    {b.status === 'sent' || b.status === 'failed' ? (
                      <span>
                        ✅ {b.sent_count}
                        {b.failed_count > 0 && (
                          <span className="text-danger"> · ❌ {b.failed_count}</span>
                        )}
                      </span>
                    ) : b.status === 'sending' ? (
                      <span className="text-muted">В процессе…</span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <div>{fmtDate(b.send_at)}</div>
                    {b.completed_at && b.status !== 'scheduled' && (
                      <div className="text-muted" style={{ fontSize: 12 }}>
                        Готово: {fmtDate(b.completed_at)}
                      </div>
                    )}
                  </td>
                  <td>
                    <div className="actions">
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        title="Просмотр"
                        onClick={() => {
                          setPreviewItem(b);
                          setPreviewOpen(true);
                        }}
                      >
                        <Eye size={16} />
                      </button>
                      {b.status === 'scheduled' && (
                        <>
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            title="Отправить сейчас"
                            onClick={() => sendNow(b.id)}
                          >
                            <Send size={16} />
                          </button>
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            title="Отменить"
                            onClick={() => cancel(b.id)}
                          >
                            <XCircle size={16} />
                          </button>
                        </>
                      )}
                      {b.status !== 'sending' && (
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm btn--danger"
                          title="Удалить"
                          onClick={() => remove(b.id)}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      </div>

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title="Новая рассылка"
        wide
        footer={
          <>
            <button type="button" className="btn btn--ghost" onClick={() => setFormOpen(false)}>
              Отмена
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={save}
              disabled={saving}
            >
              {saving ? 'Сохранение…' : sendMode === 'now' ? 'Отправить сейчас' : 'Запланировать'}
            </button>
          </>
        }
      >
        <label className="field">
          <span>Название (для себя)</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Например: Акция на лето"
          />
        </label>

        <label className="field">
          <span>Текст сообщения (HTML)</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            placeholder="Привет! У нас скидка <b>20%</b> до конца недели…"
          />
        </label>

        <label className="field">
          <span>Аудитория</span>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            {targets.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
          {countLoading ? (
            <span className="text-muted" style={{ fontSize: 12 }}>Подсчёт…</span>
          ) : recipientCount != null ? (
            <span className="text-muted" style={{ fontSize: 12 }}>
              Получателей: ~{recipientCount}
            </span>
          ) : null}
        </label>

        <label className="field">
          <span>Когда отправить</span>
          <div className="checkbox-row" style={{ gap: 16 }}>
            <label className="checkbox-row">
              <input
                type="radio"
                name="sendMode"
                checked={sendMode === 'now'}
                onChange={() => setSendMode('now')}
              />
              <Send size={16} />
              Сразу
            </label>
            <label className="checkbox-row">
              <input
                type="radio"
                name="sendMode"
                checked={sendMode === 'scheduled'}
                onChange={() => setSendMode('scheduled')}
              />
              <Clock size={16} />
              По расписанию
            </label>
          </div>
        </label>

        {sendMode === 'scheduled' && (
          <label className="field">
            <span>Дата и время (МСК)</span>
            <input
              type="datetime-local"
              value={sendAt}
              onChange={(e) => setSendAt(e.target.value)}
            />
          </label>
        )}
      </Modal>

      <Modal
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        title={previewItem?.name || `Рассылка #${previewItem?.id}`}
        wide
        footer={
          <button type="button" className="btn btn--ghost" onClick={() => setPreviewOpen(false)}>
            Закрыть
          </button>
        }
      >
        {previewItem && (
          <>
            <label className="field">
              <span>Аудитория</span>
              <p>{previewItem.target_label}</p>
            </label>
            <label className="field">
              <span>Статус</span>
              <p>
                <Badge variant={statusVariant(previewItem.status)}>
                  {STATUS_LABELS[previewItem.status]}
                </Badge>
              </p>
            </label>
            {previewItem.error_message && (
              <label className="field">
                <span>Ошибка</span>
                <p className="form-error">{previewItem.error_message}</p>
              </label>
            )}
            <label className="field">
              <span>Текст</span>
              <div
                className="card"
                style={{ padding: 12 }}
                dangerouslySetInnerHTML={{ __html: previewItem.text }}
              />
            </label>
          </>
        )}
      </Modal>
    </div>
  );
}
