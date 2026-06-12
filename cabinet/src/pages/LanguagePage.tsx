import { useState } from 'react';
import { useI18n } from '../i18n/I18nContext';

export function LanguagePage() {
  const { locale, t, setLocale, localeLabels, supportedLocales } = useI18n();
  const [saving, setSaving] = useState<string | null>(null);

  const handlePick = async (code: string) => {
    if (code === locale) return;
    setSaving(code);
    try {
      await setLocale(code);
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="page language-page">
      <header className="page-header">
        <h1>{t('language_title')}</h1>
        <p className="subtitle">{t('settings_desc')}</p>
      </header>

      <div className="lang-grid">
        {supportedLocales.map((code) => (
          <button
            key={code}
            type="button"
            className={`lang-btn ${code === locale ? 'active' : ''}`}
            disabled={saving !== null}
            onClick={() => handlePick(code)}
          >
            {localeLabels[code] || code}
            {saving === code ? '…' : code === locale ? ' ✓' : ''}
          </button>
        ))}
      </div>
    </div>
  );
}
