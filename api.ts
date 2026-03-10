import axios from 'axios';

// Определяем базовый URL для API
// В production используем относительный путь (будет работать с текущим доменом)
// В development используем localhost:8889
const getApiBaseUrl = () => {
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }
  // Если работаем на том же домене/порту, что и frontend, используем относительный путь
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return 'http://localhost:8889';
  }
  // В production используем тот же домен/порт, что и frontend
  return `${window.location.protocol}//${window.location.host}`;
};

const API_BASE_URL = getApiBaseUrl();

// Создаем экземпляр axios с базовой конфигурацией
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Интерцептор для добавления токена к каждому запросу
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token');
  if (token) {
    config.params = { ...config.params, token };
  }
  return config;
});

// Интерцептор для обработки ошибок
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Токен недействителен, перенаправляем на страницу входа
      localStorage.removeItem('admin_token');
      window.location.href = '/';
    }
    return Promise.reject(error);
  }
);

export default api;

// API функции
export const usersApi = {
  getAll: (skip = 0, limit = 100) => 
    api.get('/api/users', { params: { skip, limit } }),
  getById: (id: number) => 
    api.get(`/api/users/${id}`),
  create: (userData: any) =>
    api.post('/api/users', userData),
  update: (id: number, userData: any) =>
    api.put(`/api/users/${id}`, userData),
  delete: (id: number) =>
    api.delete(`/api/users/${id}`),
  exportCsv: () =>
    api.get('/api/users/export/csv', { responseType: 'blob' }),
  importCsv: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/api/users/import/csv', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },
  getAllWithActivationRequests: (skip = 0, limit = 100) =>
    api.get('/api/users', { params: { skip, limit, activation_requests: true } }),
  activate: (id: number) =>
    api.put(`/api/users/${id}/activate`),
  rejectActivation: (id: number) =>
    api.put(`/api/users/${id}/reject-activation`),
};

export const trafficApi = {
  getStats: (params?: { user_id?: number; start_date?: string; end_date?: string }) =>
    api.get('/api/traffic', { params }),
  getOverview: () =>
    api.get('/api/traffic/overview'),
  getUsers: (params?: { 
    period?: 'day' | 'week' | 'month' | '30days';
    search?: string;
    sort?: 'traffic_desc' | 'traffic_asc' | 'keys' | 'name';
    page?: number;
    limit?: number;
  }) =>
    api.get('/api/traffic/users', { params }),
  getUserKeys: (userId: number, period?: 'day' | 'week' | 'month' | '30days') =>
    api.get(`/api/traffic/users/${userId}/keys`, { params: { period } }),
  getChart: (params?: { 
    period?: '6hours' | 'day' | 'week' | 'month';
    vpn_key_id?: number;
    user_id?: number;
  }) =>
    api.get('/api/traffic/chart', { params }),
};

export const keysApi = {
  getAll: (params?: { user_id?: number; skip?: number; limit?: number }) =>
    api.get('/api/keys', { params }),
  activate: (id: number) =>
    api.put(`/api/keys/${id}/activate`),
  deactivate: (id: number) =>
    api.put(`/api/keys/${id}/deactivate`),
  delete: (id: number) =>
    api.delete(`/api/keys/${id}`),
};

export const authApi = {
  verify: (token: string) =>
    api.get('/api/auth/verify', { params: { token } }),
};

export const paymentsApi = {
  getAll: (params?: { 
    skip?: number; 
    limit?: number; 
    payment_type?: string; 
    status?: string;
    start_date?: string;
    end_date?: string;
  }) =>
    api.get('/api/payments', { params }),
  getStats: (params?: { start_date?: string; end_date?: string }) =>
    api.get('/api/payments/stats', { params }),
};

