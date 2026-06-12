import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Copy, ExternalLink, KeyRound, RefreshCw, Smartphone } from 'lucide-react';
import { api } from '../api/client';
import type { DashboardData } from '../types';
import { buildConnectUrl, copyToClipboard, formatBytes } from '../utils/format';
import { Spinner } from '../components/ui';

export function KeysPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [provisioning, setProvisioning] = useState(false);
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      setData(await api.dashboard());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const subUrl = data?.subscription?.subscription_url || data?.subscription?.vpn_key || '';
  const hasSub = data?.has_subscription;

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2800);
  };

  const handleCopy = async () => {
    if (!subUrl) return;
    await copyToClipboard(subUrl);
    showToast('Скопировано!');
  };

  const handleProvision = async () => {
    setProvisioning(true);
    try {
      const res = await api.provision();
      showToast(res.message || 'Ключ создан');
      await load();
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setProvisioning(false);
    }
  };

  if (loading) {
    return (
      <div className="page-loading">
        <Spinner size={32} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-error">
        <p>{error}</p>
        <button type="button" className="btn btn--primary" onClick={load}>
          <RefreshCw size={18} />
          Повторить
        </button>
      </div>
    );
  }

  if (!hasSub) {
    return (
      <div className="page">
        <header className="page-header">
          <h1>VPN-ключи</h1>
          <p className="subtitle">Сначала оформите подписку</p>
        </header>
        <section className="card empty-card">
          <KeyRound size={48} strokeWidth={1.5} />
          <p>Активная подписка нужна для получения ключа.</p>
          <Link to="/plans" className="btn btn--primary">Выбрать тариф</Link>
        </section>
      </div>
    );
  }

  const traffic = data?.subscription?.traffic;
  const used = (traffic?.up ?? 0) + (traffic?.down ?? 0);

  return (
    <div className="page">
      <header className="page-header">
        <h1>VPN-ключи</h1>
        <p className="subtitle">Ссылка подписки для VPN-приложений</p>
      </header>

      {toast && <div className="inline-toast">{toast}</div>}

      <section className="card">
        <div className="card-head">
          <h2>Ссылка подписки</h2>
          {subUrl ? (
            <button type="button" className="btn btn--ghost btn--sm" onClick={handleCopy}>
              <Copy size={16} />
              Копировать
            </button>
          ) : null}
        </div>

        {subUrl ? (
          <>
            <div className="key-box mono">{subUrl}</div>
            <p className="hint">
              Вставьте ссылку в Happ, v2rayTun или другое совместимое приложение.
            </p>
          </>
        ) : (
          <div className="empty-key">
            <p>Ключ ещё не создан. Нажмите кнопку ниже.</p>
            <button
              type="button"
              className="btn btn--primary"
              onClick={handleProvision}
              disabled={provisioning}
            >
              {provisioning ? 'Создание…' : 'Создать VPN-ключ'}
            </button>
          </div>
        )}
      </section>

      {subUrl && (
        <section className="card">
          <h2><Smartphone size={20} /> Быстрое подключение</h2>
          <p className="hint">Откройте на телефоне с установленным приложением</p>
          <div className="connect-grid">
            <a href={buildConnectUrl(subUrl, 'happ')} className="connect-btn">
              <ExternalLink size={18} />
              Happ
            </a>
            <a href={buildConnectUrl(subUrl, 'v2ray')} className="connect-btn">
              <ExternalLink size={18} />
              v2rayTun
            </a>
          </div>
        </section>
      )}

      {traffic && (
        <section className="card">
          <h2>Использование трафика</h2>
          <div className="traffic-stats">
            <div>
              <span>Загружено</span>
              <strong>{formatBytes(traffic.down)}</strong>
            </div>
            <div>
              <span>Отдано</span>
              <strong>{formatBytes(traffic.up)}</strong>
            </div>
            <div>
              <span>Всего</span>
              <strong>{formatBytes(used)}</strong>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
