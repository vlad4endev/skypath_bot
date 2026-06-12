import { useCallback, useEffect, useRef, useState } from 'react';
import { registerSW } from 'virtual:pwa-register';

const INSTALL_DISMISS_KEY = 'skypath-admin-install-dismissed';
const INSTALL_DISMISS_TTL_MS = 7 * 24 * 60 * 60 * 1000;

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

function isStandaloneMode(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    window.matchMedia('(display-mode: fullscreen)').matches ||
    (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function isIosDevice(): boolean {
  return /iPad|iPhone|iPod/.test(navigator.userAgent);
}

function isInstallDismissed(): boolean {
  try {
    const raw = localStorage.getItem(INSTALL_DISMISS_KEY);
    if (!raw) return false;
    const ts = Number(raw);
    if (Number.isNaN(ts)) return false;
    return Date.now() - ts < INSTALL_DISMISS_TTL_MS;
  } catch {
    return false;
  }
}

export function usePwa() {
  const [offline, setOffline] = useState(!navigator.onLine);
  const [needRefresh, setNeedRefresh] = useState(false);
  const [canInstall, setCanInstall] = useState(false);
  const [isStandalone, setIsStandalone] = useState(isStandaloneMode);
  const [isIos] = useState(isIosDevice);
  const [installDismissed, setInstallDismissed] = useState(isInstallDismissed);
  const deferredPrompt = useRef<BeforeInstallPromptEvent | null>(null);
  const updateSw = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle('pwa-standalone', isStandalone);

    const onStandalone = () => setIsStandalone(isStandaloneMode());
    window.matchMedia('(display-mode: standalone)').addEventListener('change', onStandalone);

    return () => {
      window.matchMedia('(display-mode: standalone)').removeEventListener('change', onStandalone);
    };
  }, [isStandalone]);

  useEffect(() => {
    const onOnline = () => setOffline(false);
    const onOffline = () => setOffline(true);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  useEffect(() => {
    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      deferredPrompt.current = e as BeforeInstallPromptEvent;
      setCanInstall(true);
    };

    window.addEventListener('beforeinstallprompt', onBeforeInstall);
    return () => window.removeEventListener('beforeinstallprompt', onBeforeInstall);
  }, []);

  useEffect(() => {
    updateSw.current = registerSW({
      immediate: true,
      onNeedRefresh() {
        setNeedRefresh(true);
      },
      onOfflineReady() {
        /* shell cached */
      },
    });
  }, []);

  const installApp = useCallback(async () => {
    const prompt = deferredPrompt.current;
    if (!prompt) return false;

    await prompt.prompt();
    const { outcome } = await prompt.userChoice;
    deferredPrompt.current = null;
    setCanInstall(false);
    return outcome === 'accepted';
  }, []);

  const dismissInstall = useCallback(() => {
    try {
      localStorage.setItem(INSTALL_DISMISS_KEY, String(Date.now()));
    } catch {
      /* ignore */
    }
    setInstallDismissed(true);
  }, []);

  const applyUpdate = useCallback(async () => {
    await updateSw.current?.();
    setNeedRefresh(false);
    window.location.reload();
  }, []);

  const showInstallBanner =
    !isStandalone &&
    !installDismissed &&
    (canInstall || isIos);

  return {
    offline,
    needRefresh,
    canInstall,
    isStandalone,
    isIos,
    showInstallBanner,
    installApp,
    dismissInstall,
    applyUpdate,
  };
}
