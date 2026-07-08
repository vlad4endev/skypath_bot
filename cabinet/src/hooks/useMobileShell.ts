import { useEffect } from 'react';

function detectPlatform() {
  const ua = navigator.userAgent;
  const isIOS =
    /iPad|iPhone|iPod/.test(ua) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isAndroid = /Android/i.test(ua);
  const nav = window.navigator as Navigator & { standalone?: boolean };
  const isStandalone =
    window.matchMedia('(display-mode: standalone)').matches || nav.standalone === true;

  return { isIOS, isAndroid, isStandalone };
}

function setViewportHeight() {
  const vh = window.visualViewport?.height ?? window.innerHeight;
  document.documentElement.style.setProperty('--vh', `${vh * 0.01}px`);
}

export function useMobileShell() {
  useEffect(() => {
    const { isIOS, isAndroid, isStandalone } = detectPlatform();
    const root = document.documentElement;

    root.classList.toggle('is-ios', isIOS);
    root.classList.toggle('is-android', isAndroid);
    root.classList.toggle('is-standalone', isStandalone);
    root.classList.toggle('is-mobile', isIOS || isAndroid || window.innerWidth < 1024);

    setViewportHeight();
    window.addEventListener('resize', setViewportHeight);
    window.visualViewport?.addEventListener('resize', setViewportHeight);
    window.visualViewport?.addEventListener('scroll', setViewportHeight);

    const onFocusIn = (e: FocusEvent) => {
      const el = e.target;
      if (
        el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement ||
        el instanceof HTMLSelectElement
      ) {
        root.classList.add('keyboard-open');
      }
    };

    const onFocusOut = () => {
      window.setTimeout(() => {
        const active = document.activeElement;
        if (
          !(active instanceof HTMLInputElement) &&
          !(active instanceof HTMLTextAreaElement) &&
          !(active instanceof HTMLSelectElement)
        ) {
          root.classList.remove('keyboard-open');
        }
      }, 120);
    };

    document.addEventListener('focusin', onFocusIn);
    document.addEventListener('focusout', onFocusOut);

    return () => {
      window.removeEventListener('resize', setViewportHeight);
      window.visualViewport?.removeEventListener('resize', setViewportHeight);
      window.visualViewport?.removeEventListener('scroll', setViewportHeight);
      document.removeEventListener('focusin', onFocusIn);
      document.removeEventListener('focusout', onFocusOut);
      root.classList.remove('is-ios', 'is-android', 'is-standalone', 'is-mobile', 'keyboard-open');
    };
  }, []);
}
