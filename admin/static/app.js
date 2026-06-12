/* SkyPath Admin Panel */
const API = '/admin/api';
let token = localStorage.getItem('admin_token') || '';
let config = {};
let charts = {};

// ── API ──────────────────────────────────────────────────────

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...opts.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  if (res.status === 401) { logout(); throw new Error('Unauthorized'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// ── Auth ─────────────────────────────────────────────────────

async function login(password) {
  const data = await api('/auth/login', { method: 'POST', body: JSON.stringify({ password }) });
  token = data.token;
  localStorage.setItem('admin_token', token);
  config = await api('/config');
  buildFilters();
  showApp();
}

function logout() {
  token = '';
  localStorage.removeItem('admin_token');
  api('/auth/logout', { method: 'POST' }).catch(() => {});
  document.getElementById('login-screen').classList.remove('hidden');
  document.getElementById('app').classList.add('hidden');
}

async function checkAuth() {
  if (!token) return false;
  try {
    await api('/auth/me');
    return true;
  } catch { return false; }
}

// ── Navigation ───────────────────────────────────────────────

const PAGES = {
  dashboard: { title: 'Аналитика', icon: '📊' },
  users: { title: 'Пользователи', icon: '👥' },
  payments: { title: 'Платежи', icon: '💰' },
  promos: { title: 'Промокоды', icon: '🎟️' },
};

let currentPage = 'dashboard';

function navigate(page) {
  currentPage = page;
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });
  document.getElementById('page-title').textContent = PAGES[page].title;
  document.querySelectorAll('.page').forEach(el => el.classList.add('hidden'));
  document.getElementById(`page-${page}`).classList.remove('hidden');
  loadPage(page);
}

async function loadPage(page) {
  switch (page) {
    case 'dashboard': return loadDashboard();
    case 'users': return loadUsers();
    case 'payments': return loadPayments();
    case 'promos': return loadPromos();
  }
}

// ── Dashboard ────────────────────────────────────────────────

async function loadDashboard() {
  const stats = await api('/stats');
  const grid = document.getElementById('stats-grid');
  const u = stats.users, s = stats.subscriptions, p = stats.payments;

  grid.innerHTML = `
    <div class="stat-card"><div class="label">Пользователей</div><div class="value">${u.total}</div><div class="sub">+${u.new_24h} за 24ч · +${u.new_7d} за 7д</div></div>
    <div class="stat-card success"><div class="label">Активных подписок</div><div class="value">${s.active}</div><div class="sub">${s.pending} ожидают · ${s.expired} истекли</div></div>
    <div class="stat-card warn"><div class="label">Истекают завтра</div><div class="value">${s.expiring_tomorrow}</div></div>
    <div class="stat-card success"><div class="label">Выручка 30д</div><div class="value">${fmtMoney(p.revenue_30d)}</div><div class="sub">${p.count_30d} платежей</div></div>
    <div class="stat-card ${p.unfulfilled ? 'danger' : ''}"><div class="label">Без VPN-ключа</div><div class="value">${p.unfulfilled}</div><div class="sub">${p.pending} ожидают оплаты</div></div>
    <div class="stat-card"><div class="label">Заблокировано</div><div class="value">${u.banned}</div><div class="sub">${stats.promos.active} активных промо</div></div>
  `;

  const [revenue, users, plans] = await Promise.all([
    api('/stats/revenue?days=30'),
    api('/stats/users?days=30'),
    api('/stats/plans'),
  ]);

  renderChart('chart-revenue', 'Выручка (₽)', revenue.map(d => d.date), revenue.map(d => d.revenue), '#6366f1');
  renderChart('chart-users', 'Новые пользователи', users.map(d => d.date), users.map(d => d.count), '#22c55e');
  renderPlanChart('chart-plans', plans);
}

function renderChart(canvasId, label, labels, data, color) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels.map(d => d.slice(5)),
      datasets: [{ label, data, borderColor: color, backgroundColor: color + '22', fill: true, tension: 0.3, pointRadius: 2 }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: '#2d3348' }, ticks: { color: '#8b92a8', maxTicksLimit: 8 } },
        y: { grid: { color: '#2d3348' }, ticks: { color: '#8b92a8' } },
      },
    },
  });
}

function renderPlanChart(canvasId, plans) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (charts[canvasId]) charts[canvasId].destroy();
  const colors = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6'];
  charts[canvasId] = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: plans.map(p => p.plan),
      datasets: [{ data: plans.map(p => p.count), backgroundColor: colors }],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'right', labels: { color: '#8b92a8' } } },
    },
  });
}

// ── Users ────────────────────────────────────────────────────

let usersPage = 1;

async function loadUsers(page = usersPage) {
  usersPage = page;
  const search = document.getElementById('users-search')?.value || '';
  const banned = document.getElementById('users-banned')?.value || '';
  const data = await api(`/users?page=${page}&search=${encodeURIComponent(search)}&banned=${banned}`);
  const tbody = document.getElementById('users-tbody');
  tbody.innerHTML = data.items.map(u => {
    const sub = u.subscription || {};
    return `
    <tr class="${u.is_banned ? 'row-banned' : ''}">
      <td>${u.id}</td>
      <td class="mono">${u.telegram_id}</td>
      <td>${u.username ? '@' + u.username : '—'}</td>
      <td>${esc(u.full_name)}${u.is_banned ? '<span class="ban-tag">бан</span>' : ''}</td>
      <td>${sub.plan ? `<span class="badge badge-accent">${sub.plan}</span>` : '—'}</td>
      <td>${sub.status ? subStatusBadge(sub) : '<span class="text-muted-sm">нет</span>'}</td>
      <td>${fmtExpiry(sub)}</td>
      <td class="actions">
        <button class="btn btn-ghost btn-sm" onclick="viewUser(${u.id})">Открыть</button>
        <button class="btn btn-sm ${u.is_banned ? 'btn-success' : 'btn-danger'}" onclick="toggleBan(${u.id}, ${!u.is_banned})">${u.is_banned ? 'Разбан' : 'Бан'}</button>
      </td>
    </tr>`;
  }).join('') || '<tr><td colspan="8" class="empty">Нет пользователей</td></tr>';
  renderPagination('users-pagination', data, loadUsers);
}

function userInitials(u, tg) {
  const name = (tg?.first_name || u.first_name || u.full_name || '?').trim();
  const parts = name.split(/\s+/);
  return (parts[0][0] + (parts[1]?.[0] || '')).toUpperCase();
}

function buildUserCardHtml(u) {
  const cur = u.subscription || {};
  const tg = u.telegram_profile || {};
  const st = u.stats || {};
  const displayName = [tg.first_name || u.first_name, tg.last_name || u.last_name].filter(Boolean).join(' ') || u.full_name;
  const username = tg.username || u.username;
  const photoHtml = `<div class="user-avatar-wrap" id="user-photo-wrap">
    <div class="user-avatar-fallback">${userInitials(u, tg)}</div>
  </div>`;

  const tgWarn = !tg.available && tg.error
    ? `<div class="tg-warn">⚠️ Telegram: ${esc(tg.error)} — пользователь мог не писать боту</div>` : '';

  return `
    <div class="modal-header">
      <h3>Карточка клиента</h3>
      <button class="btn btn-ghost btn-icon" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body">
      ${tgWarn}
      <div class="user-card-header">
        ${photoHtml}
        <div class="user-card-info">
          <h3>${esc(displayName)} ${u.is_banned ? '<span class="ban-tag">ЗАБЛОКИРОВАН</span>' : ''}</h3>
          <div class="user-card-meta">
            <span class="mono">${u.telegram_id}</span>
            ${username ? ` · <a href="https://t.me/${username}" target="_blank" rel="noopener">@${username}</a>` : ''}
            ${tg.is_premium ? ' · <span class="premium-badge">Premium</span>' : ''}
          </div>
          ${tg.bio ? `<div class="user-card-bio">${esc(tg.bio)}</div>` : ''}
          <div class="user-card-tags">
            ${cur.plan ? `<span class="badge badge-accent">${cur.plan}</span>` : ''}
            ${cur.status ? subStatusBadge(cur) : ''}
            ${u.language_code || tg.language_code ? `<span class="badge badge-muted">${tg.language_code || u.language_code}</span>` : ''}
            ${tg.profile_link ? `<a class="btn btn-ghost btn-sm" href="${tg.profile_link}" target="_blank" rel="noopener">Открыть в Telegram</a>` : ''}
          </div>
        </div>
      </div>

      <div class="user-mini-stats">
        <div class="user-mini-stat"><div class="val">${fmtMoney(st.total_spent || 0)}</div><div class="lbl">Потрачено</div></div>
        <div class="user-mini-stat"><div class="val">${st.payments_succeeded || 0}</div><div class="lbl">Оплат</div></div>
        <div class="user-mini-stat"><div class="val">${st.referrals_count || 0}</div><div class="lbl">Рефералов</div></div>
        <div class="user-mini-stat"><div class="val">${cur.days_left != null && !subIsExpired(cur) ? cur.days_left + 'д' : '—'}</div><div class="lbl">Осталось</div></div>
      </div>

      <div class="section-title">Аккаунт в боте</div>
      <div class="detail-grid">
        <div class="detail-item"><label>ID в БД</label><span>${u.id}</span></div>
        <div class="detail-item"><label>Регистрация</label><span>${fmtDate(u.created_at)}</span></div>
        <div class="detail-item"><label>Последний визит</label><span>${fmtDate(u.last_seen)}</span></div>
        <div class="detail-item"><label>Реферер (tg)</label><span class="mono">${u.referrer_id || '—'}</span></div>
        <div class="detail-item"><label>Текущий план</label><span>${cur.plan || '—'}</span></div>
        <div class="detail-item"><label>Окончание подписки</label><span>${fmtExpiry(cur)}</span></div>
      </div>

      ${tg.available ? `
      <div class="section-title">Профиль Telegram (live)</div>
      <div class="detail-grid">
        <div class="detail-item"><label>Имя в TG</label><span>${esc(tg.first_name || '—')} ${esc(tg.last_name || '')}</span></div>
        <div class="detail-item"><label>Username в TG</label><span>${tg.username ? '@' + tg.username : '—'}</span></div>
        <div class="detail-item"><label>Язык</label><span>${tg.language_code || '—'}</span></div>
        <div class="detail-item"><label>Premium</label><span>${tg.is_premium ? '✅ Да' : 'Нет'}</span></div>
      </div>` : ''}

      <div class="section-title">Подписки (${u.subscriptions.length})</div>
      ${u.subscriptions.length ? `<div class="table-wrap"><table><thead><tr>
        <th>ID</th><th>План</th><th>Статус</th><th>Начало</th><th>Окончание</th><th>Мес.</th><th>Устр.</th><th>VPN</th><th></th>
      </tr></thead><tbody>
        ${u.subscriptions.map(s => `<tr>
          <td>${s.id}</td>
          <td><span class="badge badge-accent">${s.plan}</span></td>
          <td>${subStatusBadge(s)}</td>
          <td>${fmtDate(s.started_at)}</td>
          <td>${fmtExpiry(s)}</td>
          <td>${s.months_paid || '—'}</td>
          <td>${s.limit_ip}</td>
          <td>${s.vpn_key ? '✅' : '—'}</td>
          <td><button class="btn btn-ghost btn-sm" onclick="closeModal();editSub(${s.id})">✏️</button></td>
        </tr>`).join('')}
      </tbody></table></div>` : '<p class="empty">Нет подписок</p>'}

      <div class="section-title">Платежи (${st.payments_total || u.payments.length})</div>
      ${u.payments.length ? `<div class="table-wrap"><table><thead><tr>
        <th>ID</th><th>Сумма</th><th>План</th><th>Мес.</th><th>Статус</th><th>VPN</th><th>Дата</th>
      </tr></thead><tbody>
        ${u.payments.map(p => `<tr>
          <td>${p.id}</td>
          <td>${fmtMoney(p.paid_amount || p.amount)}</td>
          <td>${p.plan || '—'}</td>
          <td>${p.months}</td>
          <td>${paymentBadge(p.status)}</td>
          <td>${p.is_fulfilled ? '🔑' : (p.status === 'succeeded' ? '⚠️' : '—')}</td>
          <td>${fmtDate(p.paid_at || p.created_at)}</td>
        </tr>`).join('')}
      </tbody></table></div>` : '<p class="empty">Нет платежей</p>'}
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">Закрыть</button>
      <button class="btn btn-${u.is_banned ? 'success' : 'ghost'}" onclick="toggleBan(${u.id}, ${!u.is_banned});closeModal()">${u.is_banned ? 'Разбанить' : 'Заблокировать'}</button>
      <button class="btn btn-danger" onclick="deleteUser(${u.id})">Удалить</button>
    </div>`;
}

async function loadUserPhoto(userId) {
  try {
    const res = await fetch(`/admin/api/users/${userId}/photo`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: 'same-origin',
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const wrap = document.getElementById('user-photo-wrap');
    if (!wrap) return;
    const img = document.createElement('img');
    img.className = 'user-avatar';
    img.src = URL.createObjectURL(blob);
    img.alt = '';
    wrap.innerHTML = '';
    wrap.appendChild(img);
  } catch { /* keep initials fallback */ }
}

async function viewUser(id) {
  const overlay = document.getElementById('modal-overlay');
  overlay.innerHTML = `<div class="modal modal-xl"><div class="modal-body"><p class="empty">Загрузка профиля из Telegram...</p></div></div>`;
  overlay.classList.remove('hidden');
  try {
    const u = await api(`/users/${id}`);
    showModal(buildUserCardHtml(u), 'modal-xl');
    if (u.telegram_profile?.has_photo) loadUserPhoto(id);
  } catch (e) {
    showModal(`<div class="modal-header"><h3>Ошибка</h3></div><div class="modal-body"><p class="error-msg">${esc(e.message)}</p></div>`, 'modal-lg');
  }
}

async function toggleBan(id, banned) {
  if (!confirm(banned ? 'Заблокировать пользователя?' : 'Разблокировать?')) return;
  await api(`/users/${id}`, { method: 'PATCH', body: JSON.stringify({ is_banned: banned }) });
  loadUsers();
}

async function deleteUser(id) {
  if (!confirm('Удалить пользователя и все связанные данные?')) return;
  await api(`/users/${id}`, { method: 'DELETE' });
  closeModal();
  loadUsers();
}

// ── Subscription edit (from user card) ───────────────────────

async function editSub(id) {
  const s = await api(`/subscriptions/${id}`);
  const statuses = (config.subscription_statuses || []).map(st =>
    `<option value="${st}" ${st === s.status ? 'selected' : ''}>${st}</option>`
  ).join('');
  const plans = (config.plan_types || []).map(p =>
    `<option value="${p}" ${p === s.plan ? 'selected' : ''}>${p}</option>`
  ).join('');
  showModal(`
    <div class="modal-header"><h3>Подписка #${s.id}</h3><button class="btn btn-ghost btn-icon" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <div class="detail-grid">
        <div class="detail-item"><label>Telegram</label><span class="mono">${s.telegram_id}</span></div>
        <div class="detail-item"><label>Дней осталось</label><span>${s.days_left}</span></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>План</label><select id="edit-sub-plan">${plans}</select></div>
        <div class="form-group"><label>Статус</label><select id="edit-sub-status">${statuses}</select></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>Продлить (дней)</label><input id="edit-sub-days" type="number" placeholder="0"></div>
        <div class="form-group"><label>Продлить (мес)</label><input id="edit-sub-months" type="number" placeholder="0"></div>
      </div>
      <div class="form-group"><label>Устройств</label><input id="edit-sub-ip" type="number" value="${s.limit_ip}"></div>
      <div class="form-group"><label>VPN ключ</label><textarea id="edit-sub-key" rows="3">${esc(s.vpn_key || '')}</textarea></div>
      <div id="edit-sub-error" class="error-msg hidden"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">Отмена</button>
      <button class="btn btn-primary" onclick="saveSub(${id})">Сохранить</button>
    </div>
  `);
}

async function saveSub(id) {
  try {
    const body = {
      plan: document.getElementById('edit-sub-plan').value,
      status: document.getElementById('edit-sub-status').value,
      limit_ip: +document.getElementById('edit-sub-ip').value,
      vpn_key: document.getElementById('edit-sub-key').value,
    };
    const days = document.getElementById('edit-sub-days').value;
    const months = document.getElementById('edit-sub-months').value;
    if (days) body.extend_days = +days;
    if (months) body.extend_months = +months;
    await api(`/subscriptions/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    closeModal();
    loadUsers();
  } catch (e) {
    const el = document.getElementById('edit-sub-error');
    el.textContent = e.message;
    el.classList.remove('hidden');
  }
}

async function deleteSub(id) {
  if (!confirm('Удалить подписку?')) return;
  await api(`/subscriptions/${id}`, { method: 'DELETE' });
  closeModal();
  loadUsers();
}

// ── Payments ─────────────────────────────────────────────────

let paymentsPage = 1;

async function loadPayments(page = paymentsPage) {
  paymentsPage = page;
  const search = document.getElementById('payments-search')?.value || '';
  const status = document.getElementById('payments-status')?.value || '';
  const unfulfilled = document.getElementById('payments-unfulfilled')?.checked ? 'true' : '';
  const data = await api(`/payments?page=${page}&search=${encodeURIComponent(search)}&status=${status}&unfulfilled=${unfulfilled}`);
  const tbody = document.getElementById('payments-tbody');
  tbody.innerHTML = data.items.map(p => `
    <tr>
      <td>${p.id}</td>
      <td class="mono truncate" title="${esc(p.order_id || '')}">${p.order_id?.slice(0, 12) || '—'}</td>
      <td class="mono">${p.telegram_id || '—'}</td>
      <td>${fmtMoney(p.paid_amount || p.amount)}</td>
      <td>${p.plan || '—'}/${p.months}м</td>
      <td>${paymentBadge(p.status)}</td>
      <td>${p.is_fulfilled ? '🔑' : (p.status === 'succeeded' ? '⚠️' : '—')}</td>
      <td>${fmtDate(p.paid_at || p.created_at)}</td>
      <td class="actions">
        ${p.status === 'succeeded' && !p.is_fulfilled ? `<button class="btn btn-success btn-sm" onclick="fulfillPayment(${p.id})">Выдать VPN</button>` : ''}
        <button class="btn btn-ghost btn-sm" onclick="viewPayment(${p.id})">Детали</button>
        <button class="btn btn-danger btn-sm" onclick="deletePayment(${p.id})">✕</button>
      </td>
    </tr>
  `).join('') || '<tr><td colspan="9" class="empty">Нет платежей</td></tr>';
  renderPagination('payments-pagination', data, loadPayments);
}

async function viewPayment(id) {
  const p = await api(`/payments/${id}`);
  showModal(`
    <div class="modal-header"><h3>Платёж #${p.id}</h3><button class="btn btn-ghost btn-icon" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <div class="detail-grid">
        <div class="detail-item"><label>Order ID</label><span class="mono">${p.order_id || '—'}</span></div>
        <div class="detail-item"><label>Provider ID</label><span class="mono">${p.yookassa_id || '—'}</span></div>
        <div class="detail-item"><label>Сумма</label><span>${fmtMoney(p.amount)} → ${p.paid_amount ? fmtMoney(p.paid_amount) : '—'}</span></div>
        <div class="detail-item"><label>Статус</label><span>${paymentBadge(p.status)} ${p.provider_status || ''}</span></div>
        <div class="detail-item"><label>План</label><span>${p.plan}/${p.months} мес</span></div>
        <div class="detail-item"><label>Telegram</label><span class="mono">${p.telegram_id || '—'}</span></div>
        <div class="detail-item"><label>Создан</label><span>${fmtDate(p.created_at)}</span></div>
        <div class="detail-item"><label>Оплачен</label><span>${fmtDate(p.paid_at)}</span></div>
        <div class="detail-item"><label>VPN выдан</label><span>${fmtDate(p.fulfilled_at) || '❌ Нет'}</span></div>
        <div class="detail-item"><label>Промокод</label><span>${p.promo_code || '—'}</span></div>
      </div>
      ${p.payment_url ? `<div class="form-group"><label>Ссылка оплаты</label><input readonly value="${esc(p.payment_url)}" onclick="this.select()"></div>` : ''}
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">Закрыть</button>
      ${p.status === 'succeeded' && !p.is_fulfilled ? `<button class="btn btn-success" onclick="fulfillPayment(${p.id})">Выдать VPN</button>` : ''}
    </div>
  `, 'modal-lg');
}

async function fulfillPayment(id) {
  if (!confirm('Выдать VPN-ключ для этого платежа?')) return;
  try {
    const r = await api(`/payments/${id}/fulfill`, { method: 'POST' });
    alert(r.ok ? 'VPN ключ выдан!' : 'Не удалось выдать ключ');
    closeModal();
    loadPayments();
  } catch (e) { alert('Ошибка: ' + e.message); }
}

async function deletePayment(id) {
  if (!confirm('Удалить платёж?')) return;
  await api(`/payments/${id}`, { method: 'DELETE' });
  loadPayments();
}

// ── Promos ─────────────────────────────────────────────────

async function loadPromos() {
  const promos = await api('/promos');
  const tbody = document.getElementById('promos-tbody');
  tbody.innerHTML = promos.map(p => `
    <tr>
      <td><strong>${p.code}</strong></td>
      <td>${p.discount_pct ? p.discount_pct + '%' : p.discount_amount + '₽'}</td>
      <td>${p.uses_count} / ${p.max_uses}</td>
      <td>${p.is_active ? (p.is_valid ? statusBadge('АКТИВНА') : statusBadge('ИСТЁК')) : statusBadge('ВЫКЛ')}</td>
      <td>${fmtDate(p.expires_at) || '∞'}</td>
      <td class="actions">
        <button class="btn btn-ghost btn-sm" onclick="editPromo(${p.id})">Изменить</button>
        <button class="btn btn-danger btn-sm" onclick="deletePromo(${p.id})">✕</button>
      </td>
    </tr>
  `).join('') || '<tr><td colspan="6" class="empty">Нет промокодов</td></tr>';
}

function showCreatePromo() {
  showModal(`
    <div class="modal-header"><h3>Новый промокод</h3><button class="btn btn-ghost btn-icon" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <div class="form-group"><label>Код *</label><input id="new-promo-code" placeholder="SKY10" style="text-transform:uppercase"></div>
      <div class="form-row">
        <div class="form-group"><label>Скидка %</label><input id="new-promo-pct" type="number" value="10"></div>
        <div class="form-group"><label>Скидка ₽</label><input id="new-promo-amt" type="number" value="0"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>Макс. использований</label><input id="new-promo-max" type="number" value="100"></div>
        <div class="form-group"><label>Истекает</label><input id="new-promo-exp" type="datetime-local"></div>
      </div>
      <div id="create-promo-error" class="error-msg hidden"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">Отмена</button>
      <button class="btn btn-primary" onclick="createPromo()">Создать</button>
    </div>
  `);
}

async function createPromo() {
  try {
    const exp = document.getElementById('new-promo-exp').value;
    await api('/promos', { method: 'POST', body: JSON.stringify({
      code: document.getElementById('new-promo-code').value,
      discount_pct: +document.getElementById('new-promo-pct').value,
      discount_amount: +document.getElementById('new-promo-amt').value,
      max_uses: +document.getElementById('new-promo-max').value,
      expires_at: exp ? new Date(exp).toISOString() : null,
    })});
    closeModal();
    loadPromos();
  } catch (e) {
    const el = document.getElementById('create-promo-error');
    el.textContent = e.message;
    el.classList.remove('hidden');
  }
}

async function editPromo(id) {
  const promos = await api('/promos');
  const p = promos.find(x => x.id === id);
  if (!p) return;
  showModal(`
    <div class="modal-header"><h3>Промокод ${p.code}</h3><button class="btn btn-ghost btn-icon" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <div class="form-row">
        <div class="form-group"><label>Скидка %</label><input id="edit-promo-pct" type="number" value="${p.discount_pct}"></div>
        <div class="form-group"><label>Скидка ₽</label><input id="edit-promo-amt" type="number" value="${p.discount_amount}"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>Макс. использований</label><input id="edit-promo-max" type="number" value="${p.max_uses}"></div>
        <div class="form-group"><label>Активен</label><select id="edit-promo-active"><option value="true" ${p.is_active?'selected':''}>Да</option><option value="false" ${!p.is_active?'selected':''}>Нет</option></select></div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">Отмена</button>
      <button class="btn btn-primary" onclick="savePromo(${id})">Сохранить</button>
    </div>
  `);
}

async function savePromo(id) {
  await api(`/promos/${id}`, { method: 'PATCH', body: JSON.stringify({
    discount_pct: +document.getElementById('edit-promo-pct').value,
    discount_amount: +document.getElementById('edit-promo-amt').value,
    max_uses: +document.getElementById('edit-promo-max').value,
    is_active: document.getElementById('edit-promo-active').value === 'true',
  })});
  closeModal();
  loadPromos();
}

async function deletePromo(id) {
  if (!confirm('Удалить промокод?')) return;
  await api(`/promos/${id}`, { method: 'DELETE' });
  loadPromos();
}

// ── Helpers ──────────────────────────────────────────────────

function fmtMoney(n) { return (n || 0).toLocaleString('ru-RU') + ' ₽'; }
function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}
function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

function statusBadge(status) {
  const map = {
    'АКТИВНА': 'success', 'ПРОБНЫЙ ПЕРИОД': 'accent', 'ОЖИДАЕТ ОПЛАТУ': 'warning',
    'ИСТЕКЛА': 'danger', 'ЗАБЛОКИРОВАНА': 'danger', 'OK': 'success', 'ВЫКЛ': 'muted', 'ИСТЁК': 'danger',
  };
  return `<span class="badge badge-${map[status] || 'muted'}">${status}</span>`;
}

function subIsExpired(sub) {
  if (!sub || !sub.status) return false;
  if (sub.is_expired) return true;
  if (sub.status === 'ИСТЕКЛА' || sub.status === 'ЗАБЛОКИРОВАНА') return true;
  if (sub.expires_at && new Date(sub.expires_at) < new Date()) return true;
  return false;
}

function subStatusBadge(sub) {
  if (!sub || !sub.status) return '<span class="text-muted-sm">нет</span>';
  if (subIsExpired(sub)) return '<span class="badge badge-danger">Истекло</span>';
  return statusBadge(sub.status);
}

function fmtExpiry(sub) {
  if (!sub || !sub.expires_at) return '<span class="text-muted-sm">—</span>';
  if (subIsExpired(sub)) {
    return `<span class="text-expired">Истекло · ${fmtDate(sub.expires_at)}</span>`;
  }
  const days = sub.days_left != null ? ` · ${sub.days_left}д` : '';
  return `${fmtDate(sub.expires_at)}${days}`;
}

function paymentBadge(status) {
  const map = { succeeded: 'success', pending: 'warning', cancelled: 'danger', refunded: 'muted' };
  const labels = { succeeded: 'Оплачен', pending: 'Ожидает', cancelled: 'Отменён', refunded: 'Возврат' };
  return `<span class="badge badge-${map[status] || 'muted'}">${labels[status] || status}</span>`;
}

function renderPagination(elId, data, loadFn) {
  const el = document.getElementById(elId);
  if (!el) return;
  const totalPages = Math.ceil(data.total / data.per_page) || 1;
  el.innerHTML = `
    <span>${data.total} записей · стр. ${data.page} из ${totalPages}</span>
    <div class="pagination-btns">
      <button class="btn btn-ghost btn-sm" ${data.page <= 1 ? 'disabled' : ''} onclick="arguments[0]; ${loadFn.name}(${data.page - 1})">← Назад</button>
      <button class="btn btn-ghost btn-sm" ${data.page >= totalPages ? 'disabled' : ''} onclick="arguments[0]; ${loadFn.name}(${data.page + 1})">Вперёд →</button>
    </div>
  `;
}

function showModal(html, cls = '') {
  const overlay = document.getElementById('modal-overlay');
  overlay.innerHTML = `<div class="modal ${cls}">${html}</div>`;
  overlay.classList.remove('hidden');
  overlay.onclick = e => { if (e.target === overlay) closeModal(); };
}

function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
}

function showApp() {
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  navigate('dashboard');
}

function buildFilters() {
  const payStatuses = (config.payment_statuses || []).map(s => `<option value="${s}">${s}</option>`).join('');
  document.getElementById('payments-status').innerHTML = '<option value="">Все статусы</option>' + payStatuses;
}

// ── Init ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('login-form').onsubmit = async e => {
    e.preventDefault();
    const err = document.getElementById('login-error');
    err.classList.add('hidden');
    try {
      await login(document.getElementById('login-password').value);
    } catch (ex) {
      err.textContent = ex.message;
      err.classList.remove('hidden');
    }
  };

  document.querySelectorAll('.nav-item').forEach(el => {
    el.onclick = () => navigate(el.dataset.page);
  });
  document.getElementById('logout-btn').onclick = logout;

  // Search debounce
  ['users-search', 'payments-search'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      let t;
      el.oninput = () => { clearTimeout(t); t = setTimeout(() => loadPage(currentPage), 400); };
    }
  });
  ['users-banned', 'payments-status', 'payments-unfulfilled'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.onchange = () => loadPage(currentPage);
  });

  if (await checkAuth()) {
    config = await api('/config');
    buildFilters();
    showApp();
  }
});
