import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import './Login.css';

const Login: React.FC = () => {
  const [searchParams] = useSearchParams();
  const { login, verifyToken } = useAuth();
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = searchParams.get('token');
    if (token) {
      handleTokenLogin(token);
    }
  }, [searchParams]);

  const handleTokenLogin = async (token: string) => {
    setLoading(true);
    setError('');
    
    try {
      login(token);
      const isValid = await verifyToken();
      if (!isValid) {
        setError('Токен недействителен или истек срок действия');
      }
    } catch (err) {
      setError('Ошибка при проверке токена');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-box">
        <h1>VPN Bot</h1>
        <h2>Админ-панель</h2>
        
        {loading ? (
          <div className="loading">Проверка токена...</div>
        ) : error ? (
          <div className="error">{error}</div>
        ) : (
          <div className="info">
            <p>Для доступа к админ-панели:</p>
            <ol>
              <li>Откройте Telegram бота</li>
              <li>Перейдите в "⚙️ Админ-панель"</li>
              <li>Нажмите "🌐 Веб-панель"</li>
              <li>Используйте ссылку с токеном</li>
            </ol>
            <p className="note">
              Или вставьте токен в URL: <code>/?token=YOUR_TOKEN</code>
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default Login;

