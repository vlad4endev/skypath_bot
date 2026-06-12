import { useState } from 'react';
import { api } from '../api/client';
import type { XuiSyncResult } from '../types';
import { Modal } from '../components/ui';

interface XuiSyncModalProps {
  open: boolean;
  userId?: number | null;
  onClose: () => void;
  onDone?: () => void;
}

const ACTION_LABEL: Record<string, string> = {
  updated: 'обновлён',
  deleted: 'удалён',
  skipped: 'пропущен',
  error: 'ошибка',
};

export function XuiSyncModal({ open, userId, onClose, onDone }: XuiSyncModalProps) {
  const [dryRun, setDryRun] = useState(false);
  const [deleteMissing, setDeleteMissing] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<XuiSyncResult | null>(null);

  const run = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const body = { dry_run: dryRun, delete_missing: deleteMissing };
      const data = userId
        ? await api.syncUserXui(userId, body)
        : await api.xuiSync(body);
      setResult(data);
      if (!dryRun) onDone?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка синхронизации');
    } finally {
      setLoading(false);
    }
  };

  const title = userId ? `Синхронизация пользователя #${userId}` : 'Массовая синхронизация с 3X-UI';

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>Закрыть</button>
          <button type="button" className="btn btn--primary" onClick={run} disabled={loading}>
            {loading ? 'Синхронизация…' : 'Запустить'}
          </button>
        </>
      }
    >
      <p className="modal-desc">
        Для каждого пользователя с VPN-подпиской запрашиваются данные из 3X-UI
        (срок, лимиты, subId, email). Данные в БД обновляются.
        Если клиента нет в панели — пользователь может быть удалён из БД вместе с платежами.
      </p>
      <label className="checkbox-row">
        <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
        <span>Только просмотр (dry run) — без изменений в БД</span>
      </label>
      <label className="checkbox-row">
        <input type="checkbox" checked={deleteMissing} onChange={(e) => setDeleteMissing(e.target.checked)} />
        <span>Удалять пользователей, отсутствующих в 3X-UI</span>
      </label>
      {error && <p className="form-error">{error}</p>}
      {result && (
        <div className="sync-result">
          <div className="sync-summary">
            <span>Обработано: <b>{result.processed}</b></span>
            <span>Обновлено: <b>{result.updated}</b></span>
            <span>Удалено: <b>{result.deleted}</b></span>
            <span>Пропущено: <b>{result.skipped}</b></span>
            <span>Ошибок: <b>{result.errors}</b></span>
            {result.dry_run && <span className="badge badge--muted">dry run</span>}
          </div>
          {result.items && result.items.length > 0 && (
            <div className="table-wrap table-wrap--scroll">
              <table>
                <thead>
                  <tr><th>User</th><th>Telegram</th><th>Действие</th><th>Детали</th></tr>
                </thead>
                <tbody>
                  {result.items.map((item, i) => (
                    <tr key={i}>
                      <td>{item.user_id}</td>
                      <td className="mono">{item.telegram_id}</td>
                      <td>{ACTION_LABEL[item.action] || item.action}</td>
                      <td>{item.message || ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
