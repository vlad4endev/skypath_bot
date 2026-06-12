import { useCallback, useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useSearchParams } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Layout } from './components/Layout';
import { LoginPage } from './pages/LoginPage';
import { HomePage } from './pages/HomePage';
import { KeysPage } from './pages/KeysPage';
import { PlansPage } from './pages/PlansPage';
import { SupportPage } from './pages/SupportPage';
import { Spinner } from './components/ui';
import { api } from './api/client';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { authenticated, loading } = useAuth();
  if (loading) {
    return (
      <div className="boot-screen">
        <Spinner size={32} />
      </div>
    );
  }
  if (!authenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function PaymentReturnHandler() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [message, setMessage] = useState<string | null>(null);

  const pollPayment = useCallback(async (orderId: string) => {
    setMessage('Проверяем оплату…');
    for (let i = 0; i < 30; i += 1) {
      try {
        const status = await api.paymentStatus(orderId);
        if (status.status === 'succeeded') {
          sessionStorage.removeItem('pending_order_id');
          setMessage('✅ Оплата прошла успешно!');
          setSearchParams({});
          return;
        }
        if (status.status === 'cancelled') {
          sessionStorage.removeItem('pending_order_id');
          setMessage('Оплата отменена');
          setSearchParams({});
          return;
        }
      } catch {
        /* retry */
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
    setMessage('Оплата обрабатывается. Обновите страницу через минуту.');
  }, [setSearchParams]);

  useEffect(() => {
    const payment = searchParams.get('payment');
    const orderId = searchParams.get('order_id') || sessionStorage.getItem('pending_order_id');
    if (payment === 'failed') {
      sessionStorage.removeItem('pending_order_id');
      setMessage('Оплата не завершена');
      setSearchParams({});
      return;
    }
    if ((payment === 'success' || orderId) && orderId) {
      pollPayment(orderId);
    }
  }, [searchParams, setSearchParams, pollPayment]);

  if (!message) return null;

  return (
    <div className="payment-banner">
      {message}
    </div>
  );
}

function AppRoutes() {
  return (
    <>
      <PaymentReturnHandler />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<HomePage />} />
          <Route path="keys" element={<KeysPage />} />
          <Route path="plans" element={<PlansPage />} />
          <Route path="support" element={<SupportPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter basename="/cabinet">
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
