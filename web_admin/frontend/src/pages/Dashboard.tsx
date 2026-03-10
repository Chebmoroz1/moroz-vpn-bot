import React, { useState, useEffect } from 'react';
import { usersApi, keysApi, trafficApi, paymentsApi } from '../services/api';
import './Dashboard.css';

interface DashboardStats {
  totalUsers: number;
  activeUsers: number;
  totalKeys: number;
  activeKeys: number;
  totalTraffic: number;
  totalPayments: number;
  totalPaymentsAmount: number;
  donationsAmount: number;
  qrSubscriptionsAmount: number;
}

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats>({
    totalUsers: 0,
    activeUsers: 0,
    totalKeys: 0,
    activeKeys: 0,
    totalTraffic: 0,
    totalPayments: 0,
    totalPaymentsAmount: 0,
    donationsAmount: 0,
    qrSubscriptionsAmount: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const [usersRes, keysRes, trafficRes, paymentsStatsRes] = await Promise.all([
        usersApi.getAll(0, 1000),
        keysApi.getAll({ limit: 1000 }),
        trafficApi.getStats(),
        paymentsApi.getStats(),
      ]);

      const users = usersRes.data;
      const keys = keysRes.data;
      const traffic = trafficRes.data;
      const paymentsStats = paymentsStatsRes.data;

      setStats({
        totalUsers: users.length,
        activeUsers: users.filter((u: any) => u.is_active).length,
        totalKeys: keys.length,
        activeKeys: keys.filter((k: any) => k.is_active).length,
        totalTraffic: traffic.reduce((sum: number, t: any) => sum + t.bytes_total, 0),
        totalPayments: paymentsStats.total_count,
        totalPaymentsAmount: paymentsStats.total_amount,
        donationsAmount: paymentsStats.donations_amount,
        qrSubscriptionsAmount: paymentsStats.qr_subscriptions_amount,
      });
    } catch (error) {
      console.error('Error loading stats:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  if (loading) {
    return <div className="dashboard-loading">Загрузка...</div>;
  }

  return (
    <div className="dashboard">
      <h1>Дашборд</h1>
      
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">👥</div>
          <div className="stat-content">
            <h3>Пользователи</h3>
            <p className="stat-value">{stats.totalUsers}</p>
            <p className="stat-label">Активных: {stats.activeUsers}</p>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">🔑</div>
          <div className="stat-content">
            <h3>Ключи</h3>
            <p className="stat-value">{stats.totalKeys}</p>
            <p className="stat-label">Активных: {stats.activeKeys}</p>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">📈</div>
          <div className="stat-content">
            <h3>Трафик (месяц)</h3>
            <p className="stat-value">{formatBytes(stats.totalTraffic)}</p>
            <p className="stat-label">За текущий месяц</p>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">💰</div>
          <div className="stat-content">
            <h3>Оплаты (месяц)</h3>
            <p className="stat-value">{stats.totalPaymentsAmount.toLocaleString('ru-RU')} ₽</p>
            <p className="stat-label">Всего: {stats.totalPayments} платежей</p>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">💚</div>
          <div className="stat-content">
            <h3>Донаты (месяц)</h3>
            <p className="stat-value">{stats.donationsAmount.toLocaleString('ru-RU')} ₽</p>
            <p className="stat-label">Добровольные пожертвования</p>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">💳</div>
          <div className="stat-content">
            <h3>Подписки QR (месяц)</h3>
            <p className="stat-value">{stats.qrSubscriptionsAmount.toLocaleString('ru-RU')} ₽</p>
            <p className="stat-label">Платные подписки</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;

