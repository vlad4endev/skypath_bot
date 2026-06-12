import { useEffect, useState } from 'react';
import { ExternalLink, MessageCircle, Monitor, Smartphone, Apple } from 'lucide-react';
import { api } from '../api/client';

const GUIDES = [
  {
    id: 'android',
    title: 'Android',
    icon: Smartphone,
    steps: [
      'Установите Happ или v2rayTun из Google Play',
      'Скопируйте ссылку подписки из раздела «Ключи»',
      'В приложении выберите «Импорт по ссылке» и вставьте URL',
      'Нажмите «Подключить»',
    ],
  },
  {
    id: 'ios',
    title: 'iPhone / iPad',
    icon: Apple,
    steps: [
      'Установите Happ или v2rayTun из App Store',
      'Откройте раздел «Ключи» и нажмите «Happ» или «v2rayTun»',
      'Подтвердите добавление подписки',
      'Включите VPN в приложении',
    ],
  },
  {
    id: 'desktop',
    title: 'Windows / macOS',
    icon: Monitor,
    steps: [
      'Установите совместимый клиент (Hiddify, Nekoray, v2rayN)',
      'Скопируйте subscription URL из кабинета',
      'Добавьте подписку через меню Import / Subscription',
      'Выберите сервер и подключитесь',
    ],
  },
];

export function SupportPage() {
  const [supportUrl, setSupportUrl] = useState('');
  const [brand, setBrand] = useState('SkyPath');
  const [openGuide, setOpenGuide] = useState<string | null>('android');

  useEffect(() => {
    api.config().then((cfg) => {
      setSupportUrl(cfg.support_url);
      setBrand(cfg.brand_name);
    }).catch(() => {});
  }, []);

  return (
    <div className="page support-page">
      <header className="page-header">
        <h1>Помощь</h1>
        <p className="subtitle">Настройка VPN и поддержка</p>
      </header>

      {supportUrl && (
        <a href={supportUrl} target="_blank" rel="noreferrer" className="card support-card">
          <MessageCircle size={28} />
          <div>
            <h2>Написать в поддержку</h2>
            <p>Ответим в Telegram в рабочее время</p>
          </div>
          <ExternalLink size={20} />
        </a>
      )}

      <section className="card">
        <h2>Как подключить VPN</h2>
        <div className="guide-tabs">
          {GUIDES.map(({ id, title, icon: Icon }) => (
            <button
              key={id}
              type="button"
              className={`guide-tab ${openGuide === id ? 'active' : ''}`}
              onClick={() => setOpenGuide(id)}
            >
              <Icon size={18} />
              {title}
            </button>
          ))}
        </div>

        {GUIDES.filter((g) => g.id === openGuide).map((guide) => (
          <ol key={guide.id} className="guide-steps">
            {guide.steps.map((step, i) => (
              <li key={step}>
                <span className="step-num">{i + 1}</span>
                {step}
              </li>
            ))}
          </ol>
        ))}
      </section>

      <section className="card legal-card">
        <h2>О сервисе</h2>
        <p>
          {brand} — защищённое VPN-подключение с шифрованием трафика.
          Управляйте подпиской в этом кабинете или через Telegram Mini App.
        </p>
      </section>
    </div>
  );
}
