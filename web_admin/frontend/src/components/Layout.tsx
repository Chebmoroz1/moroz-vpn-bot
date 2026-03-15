import React, { ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import './Layout.css';

interface LayoutProps {
  children: ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout } = useAuth();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const isActive = (path: string) => location.pathname === path;

  return (
    <div className="layout">
      <nav className="sidebar">
        <div className="sidebar-header">
          <h2>VPN Bot</h2>
          <p>Админ-панель</p>
        </div>
        <ul className="sidebar-menu">
          <li>
            <Link to="/" className={isActive('/') ? 'active' : ''}>
              📊 Дашборд
            </Link>
          </li>
          <li>
            <Link to="/users" className={isActive('/users') ? 'active' : ''}>
              👥 Пользователи
            </Link>
          </li>
          <li>
            <Link to="/traffic" className={isActive('/traffic') ? 'active' : ''}>
              📈 Трафик
            </Link>
          </li>
          <li>
            <Link to="/keys" className={isActive('/keys') ? 'active' : ''}>
              🔑 Ключи
            </Link>
          </li>
          <li>
            <Link to="/proxy" className={isActive('/proxy') ? 'active' : ''}>
              📡 MTProxy
            </Link>
          </li>
          <li>
            <Link to="/payments" className={isActive('/payments') ? 'active' : ''}>
              💰 Оплаты
            </Link>
          </li>
        </ul>
        <div className="sidebar-footer">
          <button onClick={handleLogout} className="logout-btn">
            🚪 Выход
          </button>
        </div>
      </nav>
      <main className="main-content">
        {children}
      </main>
    </div>
  );
};

export default Layout;

