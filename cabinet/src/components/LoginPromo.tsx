import { Link } from 'react-router-dom';
import { Globe, Shield, Smartphone, Sparkles, Zap } from 'lucide-react';
import { Logo } from './ui';

interface LoginPromoProps {
  brand: string;
}

const BENEFITS = [
  {
    icon: Shield,
    title: 'Приватность',
    text: 'Шифруем трафик — провайдер и Wi‑Fi не видят вашу активность.',
  },
  {
    icon: Zap,
    title: 'Скорость',
    text: 'Приоритетные серверы для стриминга, игр и работы.',
  },
  {
    icon: Globe,
    title: 'Любые сайты',
    text: 'Доступ к сервисам из любой точки мира без ограничений.',
  },
  {
    icon: Smartphone,
    title: 'До 10 устройств',
    text: 'Телефон, ноутбук, планшет — одна подписка на всю семью.',
  },
];

export function LoginPromo({ brand }: LoginPromoProps) {
  return (
    <section className="login-promo" aria-label="О сервисе">
      <div className="login-promo__glow" aria-hidden />

      <Logo brand={brand} size={52} />

      <div className="login-promo__badge">
        <Sparkles size={14} />
        <span>3 дня бесплатно · без карты</span>
      </div>

      <h1 className="login-promo__title">
        {brand}
      </h1>

      <p className="login-promo__lead">
        Быстрый и безопасный VPN с личным кабинетом — подписка, ключи и оплата в одном месте.
      </p>

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

      <p className="login-promo__footnote">
        <Link to="/">← На главную</Link>
      </p>
    </section>
  );
}
