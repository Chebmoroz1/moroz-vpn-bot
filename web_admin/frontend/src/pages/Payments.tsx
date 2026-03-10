import React, { useState, useEffect } from 'react';
import { paymentsApi } from '../services/api';
import './Payments.css';

interface Payment {
  id: number;
  user_id: number;
  amount: string;
  currency: string;
  status: string;
  payment_method: string;
  payment_type: string;
  yoomoney_payment_id: string | null;
  yoomoney_label: string;
  description: string | null;
  created_at: string;
  paid_at: string | null;
  qr_code_count: number | null;
  subscription_period_days: number | null;
  is_test: boolean;
  user_username: string | null;
  user_first_name: string | null;
  user_nickname: string | null;
}

interface PaymentStats {
  total_amount: number;
  total_count: number;
  donations_amount: number;
  donations_count: number;
  qr_subscriptions_amount: number;
  qr_subscriptions_count: number;
  success_count: number;
  pending_count: number;
  failed_count: number;
  monthly_stats: Array<{
    month: string;
    amount: number;
    count: number;
  }>;
}

const Payments: React.FC = () => {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [stats, setStats] = useState<PaymentStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [filters, setFilters] = useState({
    payment_type: '',
    status: '',
    start_date: '',
    end_date: '',
  });

  useEffect(() => {
    loadData();
  }, [filters]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [paymentsRes, statsRes] = await Promise.all([
        paymentsApi.getAll({
          limit: 1000,
          ...(filters.payment_type && { payment_type: filters.payment_type }),
          ...(filters.status && { status: filters.status }),
          ...(filters.start_date && { start_date: filters.start_date }),
          ...(filters.end_date && { end_date: filters.end_date }),
        }),
        paymentsApi.getStats({
          ...(filters.start_date && { start_date: filters.start_date }),
          ...(filters.end_date && { end_date: filters.end_date }),
        }),
      ]);

      setPayments(paymentsRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error('Error loading payments:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSync = async () => {
    try {
      setSyncing(true);
      // Вызываем синхронизацию через API yoomoney_backend
      const token = localStorage.getItem('admin_token');
      const response = await fetch(`http://moroz.myftp.biz:8888/sync_payments`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      const result = await response.json();
      console.log('Sync result:', result);
      
      // Перезагружаем данные после синхронизации
      await loadData();
    } catch (error) {
      console.error('Error syncing payments:', error);
      alert('Ошибка при синхронизации платежей');
    } finally {
      setSyncing(false);
    }
  };

  const formatDate = (dateString: string | null): string => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatAmount = (amount: string): string => {
    return `${parseFloat(amount).toLocaleString('ru-RU')} ₽`;
  };

  const getStatusBadge = (status: string): string => {
    const badges: { [key: string]: string } = {
      success: '✅ Успешно',
      pending: '⏳ Ожидание',
      failed: '❌ Ошибка',
      cancelled: '🚫 Отменено',
    };
    return badges[status] || status;
  };

  const getPaymentTypeLabel = (type: string): string => {
    const labels: { [key: string]: string } = {
      donation: '💚 Донат',
      qr_subscription: '💳 Подписка QR',
      test: '🆓 Тест',
    };
    return labels[type] || type;
  };

  const getUserDisplayName = (payment: Payment): string => {
    return payment.user_nickname || payment.user_first_name || payment.user_username || `ID: ${payment.user_id}`;
  };

  if (loading) {
    return <div className="payments-loading">Загрузка...</div>;
  }

  return (
    <div className="payments">

      {/* Статистика */}
      {stats && (
        <div className="payment-stats-grid">
          <div className="stat-card">
            <div className="stat-icon">💰</div>
            <div className="stat-content">
              <h3>Общая сумма</h3>
              <p className="stat-value">{stats.total_amount.toLocaleString('ru-RU')} ₽</p>
              <p className="stat-label">Всего платежей: {stats.total_count}</p>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">💚</div>
            <div className="stat-content">
              <h3>Донаты</h3>
              <p className="stat-value">{stats.donations_amount.toLocaleString('ru-RU')} ₽</p>
              <p className="stat-label">Количество: {stats.donations_count}</p>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">💳</div>
            <div className="stat-content">
              <h3>Подписки QR</h3>
              <p className="stat-value">{stats.qr_subscriptions_amount.toLocaleString('ru-RU')} ₽</p>
              <p className="stat-label">Количество: {stats.qr_subscriptions_count}</p>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">📊</div>
            <div className="stat-content">
              <h3>Статусы</h3>
              <p className="stat-value">✅ {stats.success_count}</p>
              <p className="stat-label">⏳ {stats.pending_count} | ❌ {stats.failed_count}</p>
            </div>
          </div>
        </div>
      )}

      {/* Кнопка синхронизации */}
      <div style={{ marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 style={{ margin: 0 }}>Статистика по оплатам</h1>
        <button 
          onClick={handleSync} 
          disabled={syncing}
          style={{
            padding: '10px 20px',
            backgroundColor: syncing ? '#ccc' : '#007bff',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: syncing ? 'not-allowed' : 'pointer',
            fontSize: '14px'
          }}
        >
          {syncing ? '⏳ Синхронизация...' : '🔄 Синхронизировать платежи'}
        </button>
      </div>

      {/* Фильтры */}
      <div className="payment-filters">
        <h2>Фильтры</h2>
        <div className="filters-grid">
          <div className="filter-group">
            <label>Тип платежа:</label>
            <select
              value={filters.payment_type}
              onChange={(e) => setFilters({ ...filters, payment_type: e.target.value })}
            >
              <option value="">Все</option>
              <option value="donation">Донаты</option>
              <option value="qr_subscription">Подписки QR</option>
              <option value="test">Тестовые</option>
            </select>
          </div>

          <div className="filter-group">
            <label>Статус:</label>
            <select
              value={filters.status}
              onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            >
              <option value="">Все</option>
              <option value="success">Успешно</option>
              <option value="pending">Ожидание</option>
              <option value="failed">Ошибка</option>
              <option value="cancelled">Отменено</option>
            </select>
          </div>

          <div className="filter-group">
            <label>С даты:</label>
            <input
              type="date"
              value={filters.start_date}
              onChange={(e) => setFilters({ ...filters, start_date: e.target.value })}
            />
          </div>

          <div className="filter-group">
            <label>По дату:</label>
            <input
              type="date"
              value={filters.end_date}
              onChange={(e) => setFilters({ ...filters, end_date: e.target.value })}
            />
          </div>
        </div>
      </div>

      {/* Таблица платежей */}
      <div className="payments-table-container">
        <h2>Список платежей ({payments.length})</h2>
        <table className="payments-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Пользователь</th>
              <th>Тип</th>
              <th>Сумма</th>
              <th>Статус</th>
              <th>Дата создания</th>
              <th>Дата оплаты</th>
              <th>Описание</th>
            </tr>
          </thead>
          <tbody>
            {payments.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: '20px' }}>
                  Платежи не найдены
                </td>
              </tr>
            ) : (
              payments.map((payment) => (
                <tr key={payment.id}>
                  <td>{payment.id}</td>
                  <td>{getUserDisplayName(payment)}</td>
                  <td>{getPaymentTypeLabel(payment.payment_type)}</td>
                  <td>{formatAmount(payment.amount)}</td>
                  <td>{getStatusBadge(payment.status)}</td>
                  <td>{formatDate(payment.created_at)}</td>
                  <td>{formatDate(payment.paid_at)}</td>
                  <td>{payment.description || '-'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Payments;

