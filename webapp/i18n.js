/** Mini App i18n — ru, en, hi, ar */
(function () {
  const SUPPORTED = ['ru', 'en', 'hi', 'ar'];
  const DEFAULT = 'ru';
  const LOCALE_LABELS = {
    ru: '🇷🇺 Русский',
    en: '🇬🇧 English',
    hi: '🇮🇳 हिन्दी',
    ar: '🇸🇦 العربية',
  };

  let locale = DEFAULT;
  let strings = {};
  let rtl = false;

  function normalize(code) {
    if (!code) return DEFAULT;
    const base = String(code).toLowerCase().split('-')[0];
    return SUPPORTED.includes(base) ? base : DEFAULT;
  }

  function t(key, params) {
    let text = strings[key] || key;
    if (params) {
      Object.keys(params).forEach((k) => {
        text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), String(params[k]));
      });
    }
    return text;
  }

  function applyBundle(bundle) {
    if (!bundle) return;
    locale = normalize(bundle.locale || locale);
    rtl = !!bundle.rtl;
    strings = { ...(bundle.app || {}), ...(bundle.lang || {}) };
    document.documentElement.lang = locale;
    document.documentElement.dir = rtl ? 'rtl' : 'ltr';
    applyNav();
    applySupportTab();
  }

  function applyNav() {
    const map = {
      home: 'nav_home',
      keys: 'nav_keys',
      plans: 'nav_plans',
      support: 'nav_support',
    };
    document.querySelectorAll('.nav-item[data-tab]').forEach((btn) => {
      const tab = btn.getAttribute('data-tab');
      const span = btn.querySelector('span:last-child');
      if (span && map[tab]) span.textContent = t(map[tab]);
    });
  }

  function applySupportTab() {
    const supportTitle = document.querySelector('#tab-support .card-title');
    if (supportTitle && !supportTitle.closest('#langCard')) {
      supportTitle.textContent = t('support_title');
    }
    const supportBtn = document.getElementById('supportBtn');
    if (supportBtn) supportBtn.textContent = '💬 ' + t('support_btn');
    renderLanguageCard();
  }

  function renderLanguageCard() {
    let card = document.getElementById('langCard');
    if (!card) {
      const host = document.getElementById('tab-support');
      if (!host) return;
      card = document.createElement('div');
      card.className = 'card';
      card.id = 'langCard';
      host.insertBefore(card, host.firstChild);
    }
    card.innerHTML = `
      <div class="card-title">🌍 ${t('language')}</div>
      <p style="font-size:14px;color:var(--muted);line-height:1.6;margin-bottom:12px">${t('language')}</p>
      <div class="lang-grid">
        ${SUPPORTED.map((code) => `
          <button type="button" class="lang-btn ${code === locale ? 'active' : ''}" data-locale="${code}" onclick="I18n.pick('${code}')">
            ${LOCALE_LABELS[code]}
          </button>`).join('')}
      </div>`;
  }

  async function pick(code) {
    const next = normalize(code);
    if (next === locale) return;
    const telegramId = window.telegramId || tg?.initDataUnsafe?.user?.id;
    if (telegramId && Number(telegramId) > 0) {
      try {
        const r = await fetch('/api/locale', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ telegram_id: Number(telegramId), locale: next }),
        });
        const data = await r.json();
        if (r.ok && data.i18n) {
          applyBundle(data.i18n);
          if (typeof window.refresh === 'function') await window.refresh();
          if (typeof window.showToast === 'function') window.showToast('✅ ' + t('language'));
          return;
        }
      } catch (e) {
        console.warn('locale save failed', e);
      }
    }
    locale = next;
    try {
      const r = await fetch(`/api/i18n/${next}`);
      const data = await r.json();
      applyBundle(data);
      if (typeof window.refresh === 'function') await window.refresh();
    } catch (e) {
      console.warn('locale load failed', e);
    }
  }

  window.I18n = {
    t,
    applyBundle,
    pick,
    get locale() { return locale; },
    get rtl() { return rtl; },
    LOCALE_LABELS,
    SUPPORTED,
  };
})();
