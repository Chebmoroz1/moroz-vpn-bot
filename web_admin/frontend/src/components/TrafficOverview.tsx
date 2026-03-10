import React, { useState, useEffect } from 'react';
import { trafficApi } from '../services/api';
import TrafficChartCard from './TrafficChartCard';
import './TrafficOverview.css';
import './TrafficChartCard.css';

interface TrafficOverviewData {
  monthly_traffic: {
    received: number;
    sent: number;
    total: number;
  };
  active_connections: {
    count: number;
    percentage: number;
    status: 'normal' | 'high' | 'critical';
  };
  chart_data: {
    '6hours': Array<{
      timestamp: string;
      label: string;
      received: number;
      sent: number;
      total: number;
    }>;
    'day': Array<{
      timestamp: string;
      label: string;
      received: number;
      sent: number;
      total: number;
    }>;
    'week': Array<{
      timestamp: string;
      label: string;
      received: number;
      sent: number;
      total: number;
    }>;
    'month': Array<{
      timestamp: string;
      label: string;
      received: number;
      sent: number;
      total: number;
    }>;
  };
}

interface TrafficOverviewProps {
  vpn_key_id?: number;
  user_id?: number;
  onFilterChange?: (vpn_key_id?: number, user_id?: number) => void;
}

const TrafficOverview: React.FC<TrafficOverviewProps> = ({ 
  vpn_key_id, 
  user_id,
  onFilterChange 
}) => {
  const [data, setData] = useState<TrafficOverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [userName, setUserName] = useState<string | undefined>(undefined);
  const [keyName, setKeyName] = useState<string | undefined>(undefined);

  useEffect(() => {
    // Перезагружаем данные при изменении фильтров
    if (vpn_key_id || user_id) {
      loadOverviewWithFilter();
      loadFilterInfo();
    } else {
      loadOverview();
      setUserName(undefined);
      setKeyName(undefined);
    }
  }, [vpn_key_id, user_id]);

  const loadFilterInfo = async () => {
    try {
      if (vpn_key_id) {
        // Загружаем информацию о ключе
        const { keysApi } = await import('../services/api');
        const response = await keysApi.getAll({ limit: 1000 });
        const key = response.data.find((k: any) => k.id === vpn_key_id);
        if (key) {
          setKeyName(key.key_name);
          setUserName(undefined);
        }
      } else if (user_id) {
        // Загружаем информацию о пользователе
        const { usersApi } = await import('../services/api');
        const response = await usersApi.getById(user_id);
        const user = response.data;
        if (user) {
          setUserName(user.nickname || user.first_name || user.username || `User #${user_id}`);
          setKeyName(undefined);
        }
      }
    } catch (error) {
      console.error('Error loading filter info:', error);
    }
  };

  const loadOverview = async () => {
    try {
      setLoading(true);
      const response = await trafficApi.getOverview();
      setData(response.data);
    } catch (error: any) {
      console.error('Error loading overview:', error);
      // Устанавливаем пустые данные при ошибке
      setData({
        monthly_traffic: { received: 0, sent: 0, total: 0 },
        active_connections: { count: 0, percentage: 0, status: 'normal' },
        chart_data: {
          '6hours': [],
          'day': [],
          'week': [],
          'month': []
        }
      });
    } finally {
      setLoading(false);
    }
  };
  
  const loadOverviewWithFilter = async () => {
    try {
      setLoading(true);
      // Загружаем данные для графиков с фильтрацией
      const [chart6h, chartDay, chartWeek, chartMonth] = await Promise.all([
        trafficApi.getChart({ period: '6hours', vpn_key_id, user_id }),
        trafficApi.getChart({ period: 'day', vpn_key_id, user_id }),
        trafficApi.getChart({ period: 'week', vpn_key_id, user_id }),
        trafficApi.getChart({ period: 'month', vpn_key_id, user_id })
      ]);
      
      // Загружаем общую информацию (без фильтрации для overview)
      const overviewResponse = await trafficApi.getOverview();
      
      // Объединяем данные
      setData({
        ...overviewResponse.data,
        chart_data: {
          '6hours': chart6h.data['6hours'] || [],
          'day': chartDay.data['day'] || [],
          'week': chartWeek.data['week'] || [],
          'month': chartMonth.data['month'] || []
        }
      });
    } catch (error: any) {
      console.error('Error loading overview with filter:', error);
      setData({
        monthly_traffic: { received: 0, sent: 0, total: 0 },
        active_connections: { count: 0, percentage: 0, status: 'normal' },
        chart_data: {
          '6hours': [],
          'day': [],
          'week': [],
          'month': []
        }
      });
    } finally {
      setLoading(false);
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'normal':
        return '#10B981'; // зеленый
      case 'high':
        return '#F59E0B'; // желтый
      case 'critical':
        return '#EF4444'; // красный
      default:
        return '#6B7280'; // серый
    }
  };

  if (loading) {
    return <div className="traffic-overview-loading">Загрузка общей статистики...</div>;
  }

  if (!data) {
    return <div className="traffic-overview-error">Ошибка загрузки данных</div>;
  }

  const { monthly_traffic, active_connections } = data;

  return (
    <div className="traffic-overview">
      <div className="traffic-overview-cards">
        {/* Карточка: Трафик за месяц */}
        <div className="overview-card traffic-card">
          <div className="overview-card-icon">📊</div>
          <div className="overview-card-content">
            <h3>Трафик за месяц</h3>
            <p className="overview-card-value">{formatBytes(monthly_traffic.total)}</p>
            <div className="overview-card-details">
              <span className="traffic-received">⬇️ {formatBytes(monthly_traffic.received)}</span>
              <span className="traffic-sent">⬆️ {formatBytes(monthly_traffic.sent)}</span>
            </div>
          </div>
        </div>

        {/* Карточка: Активные подключения */}
        <div className="overview-card connections-card">
          <div className="overview-card-icon" style={{ color: getStatusColor(active_connections.status) }}>
            🟢
          </div>
          <div className="overview-card-content">
            <h3>Активные подключения</h3>
            <p className="overview-card-value">{active_connections.count}</p>
            <div className="overview-card-details">
              <span style={{ color: getStatusColor(active_connections.status) }}>
                {active_connections.status === 'normal' ? '🟢 Норма' : 
                 active_connections.status === 'high' ? '🟡 Высокая' : '🔴 Критическая'}
              </span>
              <span className="connections-percentage">
                {active_connections.percentage.toFixed(1)}% от всех ключей
              </span>
            </div>
          </div>
        </div>

        {/* Карточка с графиком */}
        <div className="overview-card chart-card">
          <TrafficChartCard 
            chartData={data.chart_data} 
            vpn_key_id={vpn_key_id}
            user_id={user_id}
            user_name={userName}
            key_name={keyName}
            onFilterChange={onFilterChange}
          />
        </div>
      </div>
    </div>
  );
};

export default TrafficOverview;

