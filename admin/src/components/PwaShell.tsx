import { Download, RefreshCw, Share, WifiOff, X } from 'lucide-react';
import { usePwa } from '../hooks/usePwa';

export function PwaShell() {
  const {
    offline,
    needRefresh,
    canInstall,
    isIos,
    showInstallBanner,
    installApp,
    dismissInstall,
    applyUpdate,
  } = usePwa();

  return (
    <>
      {offline && (
        <div className="pwa-offline-banner" role="status">
          <WifiOff size={16} aria-hidden />
          <span>Нет сети — данные могут быть устаревшими</span>
        </div>
      )}

      {needRefresh && (
        <div className="pwa-update-banner" role="alert">
          <span>Доступна новая версия приложения</span>
          <div className="pwa-update-banner__actions">
            <button type="button" className="btn btn--sm btn--primary" onClick={() => void applyUpdate()}>
              <RefreshCw size={14} />
              Обновить
            </button>
          </div>
        </div>
      )}

      {showInstallBanner && (
        <div className="pwa-install-banner" role="dialog" aria-label="Установить приложение">
          <div className="pwa-install-banner__content">
            {isIos && !canInstall ? (
              <>
                <Share size={18} className="pwa-install-banner__icon" aria-hidden />
                <div>
                  <strong>Установите на iPhone</strong>
                  <p>
                    Нажмите «Поделиться» в Safari, затем «На экран Домой»
                  </p>
                </div>
              </>
            ) : (
              <>
                <Download size={18} className="pwa-install-banner__icon" aria-hidden />
                <div>
                  <strong>Установить SkyPath Admin</strong>
                  <p>Быстрый доступ с домашнего экрана, как нативное приложение</p>
                </div>
              </>
            )}
          </div>
          <div className="pwa-install-banner__actions">
            {canInstall && (
              <button type="button" className="btn btn--sm btn--primary" onClick={() => void installApp()}>
                Установить
              </button>
            )}
            <button
              type="button"
              className="pwa-install-banner__close"
              onClick={dismissInstall}
              aria-label="Скрыть подсказку установки"
            >
              <X size={18} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
