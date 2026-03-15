import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useSearchParams } from 'react-router-dom';
import './App.css';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Users from './pages/Users';
import Traffic from './pages/Traffic';
import Keys from './pages/Keys';
import Payments from './pages/Payments';
import Proxy from './pages/Proxy';
import Login from './pages/Login';
import { AuthProvider, useAuth } from './contexts/AuthContext';

function AppRoutes() {
  const { isAuthenticated, token, login, verifyToken } = useAuth();
  const [searchParams] = useSearchParams();
  const [checkingToken, setCheckingToken] = useState(true);
  
  // Проверяем токен из URL при первой загрузке
  useEffect(() => {
    const checkUrlToken = async () => {
      const urlToken = searchParams.get('token');
      if (urlToken && !token) {
        // Сохраняем токен из URL и проверяем его
        login(urlToken);
        const isValid = await verifyToken();
        if (isValid) {
          // Убираем token из URL
          window.history.replaceState({}, '', window.location.pathname);
        }
      }
      setCheckingToken(false);
    };
    
    checkUrlToken();
  }, [searchParams, token, login, verifyToken]);

  if (checkingToken) {
    return <div style={{ textAlign: 'center', padding: '50px' }}>Проверка авторизации...</div>;
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/users" element={<Users />} />
        <Route path="/traffic" element={<Traffic />} />
        <Route path="/keys" element={<Keys />} />
        <Route path="/payments" element={<Payments />} />
        <Route path="/proxy" element={<Proxy />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <AppRoutes />
      </Router>
    </AuthProvider>
  );
}

export default App;

