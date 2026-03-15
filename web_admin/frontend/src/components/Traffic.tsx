import React, { useState, useEffect, useCallback } from 'react';
import './Traffic.css';
import TrafficOverview from './TrafficOverview';
import TrafficUsersList from './TrafficUsersList';

const Traffic: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<'day' | 'week' | 'month' | '30days'>('month');
  const [filterUserId, setFilterUserId] = useState<number | undefined>(undefined);
  const [filterKeyId, setFilterKeyId] = useState<number | undefined>(undefined);

  const loadData = useCallback(() => {
    setLastUpdate(new Date());
  }, []);

  useEffect(() => {
    loadData();
    // Автообновление каждые 30 секунд
    const interval = setInterval(() => {
      loadData();
    }, 30000);
    return () => clearInterval(interval);
  }, [loadData]);


  const formatLastUpdate = (date: Date | null): string => {
    if (!date) return '';
    return `Обновлено: ${date.toLocaleString('ru-RU', { 
      day: '2-digit', 
      month: '2-digit', 
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })}`;
  };

  return (
    <div className="traffic">
      <div className="traffic-header">
        <h1>📊 Статистика трафика</h1>
        <div className="traffic-header-actions">
          {lastUpdate && (
            <span className="last-update">{formatLastUpdate(lastUpdate)}</span>
          )}
          <button onClick={loadData} className="refresh-btn" disabled={loading}>
            {loading ? '⏳ Обновление...' : '🔄 Обновить'}
          </button>
        </div>
      </div>

      {/* Верхний блок: Общая информация по загрузке сервера */}
      <TrafficOverview 
        user_id={filterUserId}
        vpn_key_id={filterKeyId}
        onFilterChange={(vpn_key_id, user_id) => {
          setFilterKeyId(vpn_key_id);
          setFilterUserId(user_id);
        }}
      />

      {/* Кнопка сброса фильтра, если активен */}
      {(filterUserId || filterKeyId) && (
        <div className="traffic-filter-active">
          <span>
            Фильтр активен: 
            {filterUserId && ` Пользователь ID: ${filterUserId}`}
            {filterKeyId && ` Ключ ID: ${filterKeyId}`}
          </span>
          <button 
            onClick={() => {
              setFilterUserId(undefined);
              setFilterKeyId(undefined);
            }}
            className="clear-filter-btn"
          >
            ✕ Сбросить фильтр
          </button>
        </div>
      )}

      {/* Нижний блок: Список пользователей */}
      <TrafficUsersList 
        period={selectedPeriod}
        onPeriodChange={setSelectedPeriod}
        onUserClick={(userId) => {
          setFilterUserId(userId);
          setFilterKeyId(undefined);
        }}
        onKeyClick={(keyId) => {
          setFilterKeyId(keyId);
          setFilterUserId(undefined);
        }}
      />
    </div>
  );
};

export default Traffic;
