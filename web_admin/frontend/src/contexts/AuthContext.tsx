import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authApi } from '../services/api';

interface AuthContextType {
  token: string | null;
  isAuthenticated: boolean;
  login: (token: string) => void;
  logout: () => void;
  verifyToken: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => {
    return localStorage.getItem('admin_token');
  });
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    if (token) {
      verifyToken();
    }
  }, [token]);

  const verifyToken = async (): Promise<boolean> => {
    if (!token) {
      setIsAuthenticated(false);
      return false;
    }

    try {
      // Используем authApi, который автоматически добавит токен в query params
      const response = await authApi.verify(token);
      
      if (response.data.valid) {
        setIsAuthenticated(true);
        return true;
      } else {
        logout();
        return false;
      }
    } catch (error: any) {
      console.error('Token verification failed:', error);
      // Если ошибка 401 (неавторизован), не делаем logout, т.к. это может быть из-за неправильного URL
      if (error?.response?.status === 401) {
        logout();
        return false;
      }
      // Для других ошибок (например, сетевые) не делаем logout
      return false;
    }
  };

  const login = (newToken: string) => {
    setToken(newToken);
    localStorage.setItem('admin_token', newToken);
    setIsAuthenticated(true);
  };

  const logout = () => {
    setToken(null);
    localStorage.removeItem('admin_token');
    setIsAuthenticated(false);
  };

  return (
    <AuthContext.Provider value={{ token, isAuthenticated, login, logout, verifyToken }}>
      {children}
    </AuthContext.Provider>
  );
};

