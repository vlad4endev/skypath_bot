import { useEffect, useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { ArrowRight, Globe, Shield, Sparkles, Zap } from 'lucide-react';
import { api } from '../api/client';
import type { PlanInfo } from '../types';
import { Logo } from '../components/ui';
import { useAuth } from '../context/AuthContext';

const PLAN_ORDER = ['BASIC', 'MULTI', 'SUPER'];

export function LandingPage() {
  const { authenticated, loading } = useAuth();
  const [brand, setBrand] = useState('SkyPath VPN');
  const [plans, setPlans] = useState<Record<string, PlanInfo>>({});

  useEffect(() => {
    api.publicPlans().then((res) => {
      setBrand(res.brand_name || 'SkyPath VPN');
      setPlans(res.plans || {});
    }).catch(() => {});
  }, []);

  if (loading) return null;
  if (authenticated) return <Navigate to="/app" replace />;

  return (
    <div className="landing">
      <div className="landing-aurora" aria-hidden />
      <div className="landing-grid" aria-hidden />

      <header className="landing-nav">
        <Logo brand={brand} size={40} />
        <nav className="landing-nav__links">
          <a href="#plans">Тарифы</a>
          <a href="#features">Возможности</a>
          <Link to="/login" className="btn btn--ghost btn--sm">Войти</Link>
          <Link to="/register" className="btn btn--primary btn--sm">
            Начать бесплатно
            <ArrowRight size={16} />
          </Link>
        </nav>
      </header>

      <section className="landing-hero">
        <div className="landing-hero__visual" aria-hidden>
          <div className="orbit orbit--1" />
          <div className="orbit orbit--2" />
          <div className="globe-wire" />
        </div>

        <div className="landing-hero__copy">
          <p className="landing-eyebrow">
            <Sparkles size={14} />
            3 дня бесплатно · без привязки карты
          </p>
          <h1 className="landing-hero__brand">{brand}</h1>
          <p className="landing-hero__tagline">
            Быстрый VPN с личным кабинетом — подписка, ключи и оплата в одном месте.
          </p>
          <div className="landing-hero__cta">
            <Link to="/register" className="btn btn--primary btn--lg">
              Попробовать бесплатно
              <ArrowRight size={20} />
            </Link>
            <Link to="/login" className="btn btn--secondary btn--lg">
              У меня есть аккаунт
            </Link>
          </div>
        </div>
      </section>

      <section id="features" className="landing-section">
        <h2>Почему {brand}</h2>
        <div className="feature-strip">
          <article className="feature-item">
            <Shield size={22} />
            <div>
              <h3>Шифрование</h3>
              <p>Трафик защищён в любой сети — дома, в кафе, в роуминге.</p>
            </div>
          </article>
          <article className="feature-item">
            <Zap size={22} />
            <div>
              <h3>Скорость</h3>
              <p>Стриминг в 4K, игры и мессенджеры без просадок.</p>
            </div>
          </article>
          <article className="feature-item">
            <Globe size={22} />
            <div>
              <h3>Локации</h3>
              <p>Россия, США, Германия, Нидерланды, Казахстан.</p>
            </div>
          </article>
        </div>
      </section>

      <section id="plans" className="landing-section">
        <h2>Тарифы</h2>
        <p className="landing-section__lead">Честные цены — без скрытых платежей</p>
        <div className="landing-plans">
          {PLAN_ORDER.filter((k) => plans[k]).map((key) => {
            const plan = plans[key];
            const minPrice = plan.prices
              ? Math.min(...Object.values(plan.prices))
              : plan.price;
            return (
              <article
                key={key}
                className={`landing-plan ${plan.recommended ? 'landing-plan--featured' : ''}`}
              >
                {plan.recommended && <span className="landing-plan__badge">Популярный</span>}
                <h3>{plan.name}</h3>
                <p>{plan.description}</p>
                <div className="landing-plan__price">
                  от <strong>{minPrice} ₽</strong>/мес
                </div>
                <ul>
                  {plan.features.slice(0, 4).map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              </article>
            );
          })}
        </div>
        <div className="landing-section__cta">
          <Link to="/register" className="btn btn--primary btn--lg">
            Создать аккаунт и выбрать тариф
          </Link>
        </div>
      </section>

      <footer className="landing-footer">
        <Logo brand={brand} size={32} />
        <p>© {new Date().getFullYear()} {brand}</p>
      </footer>

      <div className="landing-mobile-cta">
        <Link to="/register" className="btn btn--primary btn--block btn--lg">
          Попробовать бесплатно
          <ArrowRight size={18} />
        </Link>
      </div>
    </div>
  );
}
