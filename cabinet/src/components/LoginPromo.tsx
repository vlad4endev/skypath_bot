import { Globe, Shield, Smartphone, Sparkles, Zap } from 'lucide-react';
import { Logo } from './ui';

interface LoginPromoProps {
  brand: string;
  botUsername?: string;
}

const BENEFITS = [
  {
    icon: Shield,
    title: 'Приватность',
    text: 'Шифруем трафик — провайдер и Wi‑Fi не видят, что вы делаете в сети.',
  },
  {
    icon: Zap,
    title: 'Скорость',
    text: 'Серверы с высоким приоритетом — стриминг и игры без лагов.',
  },
  {
    icon: Globe,
    title: 'Любые сайты',
    text: 'Обход блокировок и доступ к сервисам из любой точки мира.',
  },
  {
    icon: Smartphone,
    title: 'До 10 устройств',
    text: 'Телефон, ноутбук, планшет — одна подписка на всю семью.',
  },
];

export function LoginPromo({ brand, botUsername }: LoginPromoProps) {
  return (
    <section className="login-promo" aria-label="О сервисе">
      <div className="login-promo__glow" aria-hidden />

      <Logo brand={brand} size={52} />

      <div className="login-promo__badge">
        <Sparkles size={14} />
        <span>3 дня бесплатно · без карты</span>
      </div>

      <h1 className="login-promo__title">
        VPN, который просто&nbsp;работает
      </h1>

      <p className="login-promo__lead">
        {brand} — быстрый и безопасный доступ в интернет.
        Личный кабинет — ваш центр управления: подписка, ключи и оплата в одном месте.
      </p>

      <div className="login-promo__stats">
        <div className="login-promo__stat">
          <strong>5+</strong>
          <span>локаций</span>
        </div>
        <div className="login-promo__stat">
          <strong>∞</strong>
          <span>трафик</span>
        </div>
        <div className="login-promo__stat">
          <strong>24/7</strong>
          <span>поддержка</span>
        </div>
      </div>

      <div className="login-promo__cards">
        {BENEFITS.map(({ icon: Icon, title, text }) => (
          <article key={title} className="login-promo__card">
            <div className="login-promo__card-icon">
              <Icon size={20} />
            </div>
            <div>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          </article>
        ))}
      </div>

      {!botUsername && (
        <p className="login-promo__footnote">
          Подключение за 2 минуты: регистрация в боте → ключ → приложение Happ или v2rayTun.
        </p>
      )}
      {botUsername && (
        <p className="login-promo__footnote">
          Нет аккаунта?{' '}
          <a href={`https://t.me/${botUsername}`} target="_blank" rel="noreferrer">
            Откройте @{botUsername}
          </a>
          {' '}— пробный период за пару кликов.
        </p>
      )}
    </section>
  );
}
