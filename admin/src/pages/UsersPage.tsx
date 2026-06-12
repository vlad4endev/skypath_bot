import { useCallback, useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { api } from '../api/client';
import type { UserRow } from '../types';
import { Pagination, Spinner } from '../components/ui';
import { daysLeftClass, fmtDaysLeft, pagesCount } from '../utils/format';
import { UserCardModal } from '../modals/UserCardModal';

interface UsersPageProps {
  onXuiSync: (userId: number) => void;
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
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

  return (
    <div className="page">
      <header className="page-top-bar">
        <h1 className="page-top-bar__title">Пользователи</h1>
        <div className="page-top-bar__actions">
          <label className="toolbar-field toolbar-field--search">
            <Search size={16} aria-hidden />
            <input
              type="search"
              placeholder="ID, имя, username…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <select
            value={banned}
            onChange={(e) => setBanned(e.target.value)}
            className="toolbar-field toolbar-field--select"
            aria-label="Фильтр по бану"
          >
            <option value="">Все</option>
            <option value="true">Заблокированные</option>
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
                    <th>Имя</th>
                    <th>Username</th>
                    <th>Окончание</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {items.length === 0 ? (
                    <tr><td colSpan={5} className="empty-cell">Нет пользователей</td></tr>
                  ) : (
                    items.map((u) => {
                      const sub = u.subscription;
                      return (
                        <tr key={u.id} className={u.is_banned ? 'row-banned' : ''}>
                          <td>{u.id}</td>
                          <td>{u.full_name}</td>
                          <td>{u.username ? `@${u.username}` : '—'}</td>
                          <td className={daysLeftClass(sub)}>{fmtDaysLeft(sub)}</td>
                          <td className="actions">
                            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setSelectedId(u.id)}>
                              Открыть
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
