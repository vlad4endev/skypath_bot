import { useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Layout } from './components/Layout';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { UsersPage } from './pages/UsersPage';
import { PaymentsPage } from './pages/PaymentsPage';
import { PromosPage } from './pages/PromosPage';
import { XuiSyncModal } from './modals/XuiSyncModal';
import { useToast } from './components/ui';

function AppRoutes() {
  const { loading, authenticated } = useAuth();
  const { show, ToastEl } = useToast();
  const [xuiOpen, setXuiOpen] = useState(false);
  const [xuiUserId, setXuiUserId] = useState<number | null>(null);

  const openXuiSync = (userId?: number) => {
    setXuiUserId(userId ?? null);
    setXuiOpen(true);
  };

  if (loading) {
    return (
      <div className="boot-screen">
        <div className="spinner" style={{ width: 36, height: 36 }} />
      </div>
    );
  }

  if (!authenticated) {
    return (
      <>
        <LoginPage />
        {ToastEl}
      </>
    );
  }

  return (
    <>
      <BrowserRouter basename="/admin">
        <Routes>
          <Route
            element={
              <Layout onXuiSync={() => openXuiSync()} />
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="users" element={<UsersPage onXuiSync={(id) => openXuiSync(id)} onToast={show} />} />
            <Route path="payments" element={<PaymentsPage onToast={show} />} />
            <Route path="promos" element={<PromosPage onToast={show} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>

      <XuiSyncModal
        open={xuiOpen}
        userId={xuiUserId}
        onClose={() => setXuiOpen(false)}
        onDone={() => show('Синхронизация завершена', 'success')}
      />

      {ToastEl}
    </>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
