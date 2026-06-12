import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { api } from '../api/client';

type I18nStrings = Record<string, string>;

interface I18nBundle {
  locale: string;
  rtl: boolean;
  cabinet?: I18nStrings;
  app?: I18nStrings;
  lang?: I18nStrings;
  locale_labels?: Record<string, string>;
  supported_locales?: string[];
}

interface I18nState {
  locale: string;
  rtl: boolean;
  ready: boolean;
  t: (key: string, params?: Record<string, string | number>) => string;
  setLocale: (code: string) => Promise<void>;
  localeLabels: Record<string, string>;
  supportedLocales: string[];
}

const LOCALE_LABELS: Record<string, string> = {
  ru: '🇷🇺 Русский',
  en: '🇬🇧 English',
  hi: '🇮🇳 हिन्दी',
  ar: '🇸🇦 العربية',
};

const I18nContext = createContext<I18nState | null>(null);

function applyRtl(locale: string, rtl: boolean) {
  document.documentElement.lang = locale;
  document.documentElement.dir = rtl ? 'rtl' : 'ltr';
}

function mergeStrings(bundle: I18nBundle | null | undefined): I18nStrings {
  if (!bundle) return {};
  return { ...(bundle.cabinet || {}), ...(bundle.app || {}), ...(bundle.lang || {}) };
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState('ru');
  const [rtl, setRtl] = useState(false);
  const [strings, setStrings] = useState<I18nStrings>({});
  const [ready, setReady] = useState(false);
  const [localeLabels, setLocaleLabels] = useState(LOCALE_LABELS);
  const [supportedLocales, setSupportedLocales] = useState(['ru', 'en', 'hi', 'ar']);

  const applyBundle = useCallback((bundle: I18nBundle) => {
    const loc = bundle.locale || 'ru';
    setLocaleState(loc);
    setRtl(!!bundle.rtl);
    setStrings(mergeStrings(bundle));
    if (bundle.locale_labels) setLocaleLabels(bundle.locale_labels);
    if (bundle.supported_locales) setSupportedLocales(bundle.supported_locales);
    applyRtl(loc, !!bundle.rtl);
  }, []);

  useEffect(() => {
    api.config().then((cfg) => {
      if (cfg.i18n) applyBundle(cfg.i18n as unknown as I18nBundle);
      else if (cfg.locale) applyRtl(cfg.locale, cfg.locale === 'ar');
    }).catch(() => {}).finally(() => setReady(true));
  }, [applyBundle]);

  const t = useCallback(
    (key: string, params?: Record<string, string | number>) => {
      let text = strings[key] || key;
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v));
        });
      }
      return text;
    },
    [strings],
  );

  const setLocale = useCallback(async (code: string) => {
    const res = await api.setLocale(code);
    if (res.i18n) applyBundle(res.i18n as I18nBundle);
  }, [applyBundle]);

  const hydrateFromAuth = useCallback((bundle: I18nBundle | undefined) => {
    if (bundle) applyBundle(bundle);
  }, [applyBundle]);

  const value = useMemo(
    () => ({
      locale,
      rtl,
      ready,
      t,
      setLocale,
      localeLabels,
      supportedLocales,
      hydrateFromAuth,
    }),
    [locale, rtl, ready, t, setLocale, localeLabels, supportedLocales, hydrateFromAuth],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nState & { hydrateFromAuth: (bundle: I18nBundle | undefined) => void } {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n outside I18nProvider');
  return ctx as I18nState & { hydrateFromAuth: (bundle: I18nBundle | undefined) => void };
}

export type { I18nBundle };
