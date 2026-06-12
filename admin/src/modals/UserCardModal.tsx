import { useEffect, useState } from 'react';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { api, getToken } from '../api/client';
import type { UserDetail } from '../types';
import { Badge, Modal, Spinner } from '../components/ui';
import { fmtDate, fmtExpiry, fmtMoney, subIsExpired, userInitials } from '../utils/format';
import { EditSubModal } from './EditSubModal';

interface UserCardModalProps {
  userId: number | null;
  onClose: () => void;
  onRefresh: () => void;
  onXuiSync: (userId: number) => void;
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

function subBadge(sub: { status?: string | null; is_expired?: boolean }) {
  if (!sub.status) return <Badge variant="muted">нет</Badge>;
  if (subIsExpired(sub)) return <Badge variant="danger">{sub.status}</Badge>;
  if (sub.status === 'АКТИВНА') return <Badge variant="success">{sub.status}</Badge>;
  return <Badge>{sub.status}</Badge>;
}

export function UserCardModal({ userId, onClose, onRefresh, onXuiSync, onToast }: UserCardModalProps) {
  const [user, setUser] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [editSubId, setEditSubId] = useState<number | null>(null);

  const load = async (id: number) => {
    setLoading(true);
    try {
      const data = await api.userDetail(id);
      setUser(data);
      if (data.telegram_profile?.has_photo) {
        const token = getToken();
        const res = await fetch(`/admin/api/users/${id}/photo`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          credentials: 'same-origin',
        });
        if (res.ok) {
          const blob = await res.blob();
          setPhotoUrl(URL.createObjectURL(blob));
        }
      } else {
        setPhotoUrl(null);
      }
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Ошибка загрузки', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (userId) load(userId);
    return () => {
      if (photoUrl) URL.revokeObjectURL(photoUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const toggleBan = async () => {
    if (!user) return;
    const banned = !user.is_banned;
    if (!confirm(banned ? 'Заблокировать пользователя?' : 'Разблокировать?')) return;
    await api.banUser(user.id, banned);
    onToast(banned ? 'Пользователь заблокирован' : 'Разблокирован', 'success');
    load(user.id);
    onRefresh();
  };

  const deleteUser = async () => {
    if (!user) return;
    if (!confirm('Удалить пользователя и все связанные данные?')) return;
    await api.deleteUser(user.id);
    onToast('Пользователь удалён', 'success');
    onClose();
    onRefresh();
  };

  const tg = user?.telegram_profile;
  const cur = user?.subscription;
  const st = user?.stats;

  return (
    <>
      <Modal
        open={userId !== null}
        onClose={onClose}
        title="Карточка клиента"
        wide
        footer={
          user && (
            <>
              <button type="button" className="btn btn--ghost" onClick={onClose}>
                Закрыть
              </button>
              <button type="button" className="btn btn--primary" onClick={() => onXuiSync(user.id)}>
                <RefreshCw size={16} /> Синхр. 3X-UI
              </button>
              <button
                type="button"
                className={`btn ${user.is_banned ? 'btn--success' : 'btn--ghost'}`}
                onClick={toggleBan}
              >
                {user.is_banned ? 'Разбанить' : 'Заблокировать'}
              </button>
              <button type="button" className="btn btn--danger" onClick={deleteUser}>
                Удалить
              </button>
            </>
          )
        }
      >
        {loading && (
          <div className="page-loading">
            <Spinner />
            <p>Загрузка профиля из Telegram…</p>
          </div>
        )}
        {!loading && user && (
          <>
            {tg && !tg.available && tg.error && (
              <p className="banner banner--warn">Telegram: {tg.error}</p>
            )}
            <div className="user-card-header">
              <div className="user-avatar-wrap">
                {photoUrl ? (
                  <img src={photoUrl} alt="" className="user-avatar" />
                ) : (
                  <div className="user-avatar-fallback">
                    {userInitials(tg?.first_name || user.first_name, tg?.last_name || user.last_name, user.full_name)}
                  </div>
                )}
              </div>
              <div className="user-card-info">
                <h3>
                  {[tg?.first_name || user.first_name, tg?.last_name || user.last_name].filter(Boolean).join(' ') ||
                    user.full_name}
                  {user.is_banned && <Badge variant="danger">ЗАБЛОКИРОВАН</Badge>}
                </h3>
                <div className="user-card-meta">
                  <span className="mono">{user.telegram_id}</span>
                  {(tg?.username || user.username) && (
                    <>
                      {' · '}
                      <a
                        href={`https://t.me/${tg?.username || user.username}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        @{tg?.username || user.username}
                      </a>
                    </>
                  )}
                  {tg?.is_premium && <Badge variant="warning">Premium</Badge>}
                </div>
                {tg?.bio && <p className="user-card-bio">{tg.bio}</p>}
                <div className="user-card-tags">
                  {cur?.plan && <Badge variant="default">{cur.plan}</Badge>}
                  {cur?.status && subBadge(cur)}
                  {(user.language_code || tg?.language_code) && (
                    <Badge variant="muted">{tg?.language_code || user.language_code}</Badge>
                  )}
                  {tg?.profile_link && (
                    <a href={tg.profile_link} target="_blank" rel="noopener noreferrer" className="btn btn--ghost btn--sm">
                      <ExternalLink size={14} /> Telegram
                    </a>
                  )}
                </div>
              </div>
            </div>

            <div className="user-mini-stats">
              <div className="user-mini-stat">
                <div className="val">{fmtMoney(st?.total_spent || 0)}</div>
                <div className="lbl">Потрачено</div>
              </div>
              <div className="user-mini-stat">
                <div className="val">{st?.payments_succeeded || 0}</div>
                <div className="lbl">Оплат</div>
              </div>
              <div className="user-mini-stat">
                <div className="val">{st?.referrals_count || 0}</div>
                <div className="lbl">Рефералов</div>
              </div>
              <div className="user-mini-stat">
                <div className="val">
                  {cur && !subIsExpired(cur) && cur.days_left != null ? `${cur.days_left}д` : '—'}
                </div>
                <div className="lbl">Осталось</div>
              </div>
            </div>

            <h4 className="section-title">Аккаунт в боте</h4>
            <div className="detail-grid">
              <div className="detail-item"><label>ID в БД</label><span>{user.id}</span></div>
              <div className="detail-item"><label>Регистрация</label><span>{fmtDate(user.created_at)}</span></div>
              <div className="detail-item"><label>Последний визит</label><span>{fmtDate(user.last_seen)}</span></div>
              <div className="detail-item"><label>Реферер</label><span className="mono">{user.referrer_id || '—'}</span></div>
              <div className="detail-item"><label>Текущий план</label><span>{cur?.plan || '—'}</span></div>
              <div className="detail-item"><label>Окончание</label><span>{fmtExpiry(cur)}</span></div>
            </div>

            <h4 className="section-title">Подписки ({user.subscriptions.length})</h4>
            {user.subscriptions.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th><th>План</th><th>Статус</th><th>Начало</th><th>Окончание</th><th>Мес.</th><th>Устр.</th><th>VPN</th><th />
                    </tr>
                  </thead>
                  <tbody>
                    {user.subscriptions.map((s) => (
                      <tr key={s.id}>
                        <td>{s.id}</td>
                        <td><Badge>{s.plan}</Badge></td>
                        <td>{subBadge(s)}</td>
                        <td>{fmtDate(s.started_at)}</td>
                        <td className={s.is_expired ? 'text-danger' : ''}>{fmtExpiry(s)}</td>
                        <td>{s.months_paid ?? '—'}</td>
                        <td>{s.limit_ip}</td>
                        <td>{s.vpn_key ? '✓' : '—'}</td>
                        <td>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditSubId(s.id)}>
                            ✏️
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty-inline">Нет подписок</p>
            )}

            <h4 className="section-title">Платежи ({st?.payments_total || user.payments.length})</h4>
            {user.payments.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th><th>Сумма</th><th>План</th><th>Мес.</th><th>Статус</th><th>VPN</th><th>Дата</th>
                    </tr>
                  </thead>
                  <tbody>
                    {user.payments.map((p) => (
                      <tr key={p.id}>
                        <td>{p.id}</td>
                        <td>{fmtMoney(p.paid_amount || p.amount)}</td>
                        <td>{p.plan || '—'}</td>
                        <td>{p.months ?? '—'}</td>
                        <td><Badge variant={p.status === 'succeeded' ? 'success' : 'muted'}>{p.status}</Badge></td>
                        <td>{p.is_fulfilled ? '🔑' : p.status === 'succeeded' ? '⚠️' : '—'}</td>
                        <td>{fmtDate(p.paid_at || p.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty-inline">Нет платежей</p>
            )}
          </>
        )}
      </Modal>

      <EditSubModal
        subId={editSubId}
        onClose={() => setEditSubId(null)}
        onSaved={() => userId && load(userId)}
        onToast={onToast}
      />
    </>
  );
}
