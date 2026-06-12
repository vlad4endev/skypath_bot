import { useCallback, useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { api } from '../api/client';
import type { UserRow } from '../types';
import { Badge, Pagination, Spinner } from '../components/ui';
import { fmtExpiry, pagesCount, subIsExpired } from '../utils/format';
import { UserCardModal } from '../modals/UserCardModal';

interface UsersPageProps {
  onXuiSync: (userId: number) => void;
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

function subBadge(sub: UserRow['subscription']) {
  if (!sub?.status) return <Badge variant="muted">нет</Badge>;
  if (subIsExpired(sub)) return <Badge variant="danger">{sub.status}</Badge>;
  if (sub.status === 'АКТИВНА') return <Badge variant="success">{sub.status}</Badge>;
  return <Badge>{sub.status}</Badge>;
}

export function UsersPage({ onXuiSync, onToast }: UsersPageProps) {
  const [items, setItems] = useState<UserRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [perPage] = useState(20);
  const [search, setSearch] = useState('');
  const [banned, setBanned] = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const load = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const data = await api.users(p, search, banned);
      setItems(data.items);
      setTotal(data.total);
      setPage(data.page);
    } finally {
      setLoading(false);
    }
  }, [page, search, banned]);

  useEffect(() => {
    load(1);
  }, [search, banned]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load(page);
  }, [page]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleBan = async (u: UserRow) => {
    const next = !u.is_banned;
    if (!confirm(next ? 'Заблокировать пользователя?' : 'Разблокировать?')) return;
    await api.banUser(u.id, next);
    onToast(next ? 'Заблокирован' : 'Разблокирован', 'success');
    load(page);
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Пользователи</h1>
          <p className="page-desc">Управление клиентами и подписками</p>
        </div>
        <div className="page-toolbar">
          <div className="search-wrap">
            <Search size={18} />
            <input
              type="search"
              placeholder="Поиск: ID, username, имя…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select value={banned} onChange={(e) => setBanned(e.target.value)} className="select-filter">
            <option value="">Все</option>
            <option value="true">Только заблокированные</option>
            <option value="false">Без бана</option>
          </select>
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
                    <th>Telegram</th>
                    <th>Username</th>
                    <th>Имя</th>
                    <th>План</th>
                    <th>Статус</th>
                    <th>Окончание</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {items.length === 0 ? (
                    <tr><td colSpan={8} className="empty-cell">Нет пользователей</td></tr>
                  ) : (
                    items.map((u) => {
                      const sub = u.subscription;
                      return (
                        <tr key={u.id} className={u.is_banned ? 'row-banned' : ''}>
                          <td>{u.id}</td>
                          <td className="mono">{u.telegram_id}</td>
                          <td>{u.username ? `@${u.username}` : '—'}</td>
                          <td>
                            {u.full_name}
                            {u.is_banned && <Badge variant="danger">бан</Badge>}
                          </td>
                          <td>{sub?.plan ? <Badge>{sub.plan}</Badge> : '—'}</td>
                          <td>{subBadge(sub)}</td>
                          <td className={subIsExpired(sub) ? 'text-danger' : ''}>{fmtExpiry(sub)}</td>
                          <td className="actions">
                            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setSelectedId(u.id)}>
                              Открыть
                            </button>
                            <button
                              type="button"
                              className={`btn btn--sm ${u.is_banned ? 'btn--success' : 'btn--danger'}`}
                              onClick={() => toggleBan(u)}
                            >
                              {u.is_banned ? 'Разбан' : 'Бан'}
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pages={pagesCount(total, perPage)} onPage={setPage} />
          </>
        )}
      </div>

      <UserCardModal
        userId={selectedId}
        onClose={() => setSelectedId(null)}
        onRefresh={() => load(page)}
        onXuiSync={(id) => {
          setSelectedId(null);
          onXuiSync(id);
        }}
        onToast={onToast}
      />
    </div>
  );
}
