import React, { useState, useEffect } from 'react';
import { trafficApi } from '../services/api';
import './TrafficUserCard.css';

interface UserTrafficStat {
  user_id: number;
  user_name: string;
  username: string | null;
  nickname: string | null;
  is_admin: boolean;
  total_traffic: number;
  received: number;
  sent: number;
  keys_count: number;
  active_keys_count: number;
  last_connection: string | null;
}

interface UserKeyStat {
  vpn_key_id: number;
  key_name: string;
  is_active: boolean;
  received: number;
  sent: number;
  total: number;
  last_connection: string | null;
  connection_ips: string[];
  uptime_seconds: number | null;
  client_ip: string | null;
  ip_city?: string | null;
  ip_provider?: string | null;
}

interface UserKeysResponse {
  user_id: number;
  user_name: string;
  period: string;
  summary: {
    total_received: number;
    total_sent: number;
    total_traffic: number;
    active_keys_count: number;
    total_keys_count: number;
    last_connection: string | null;
  };
  keys: UserKeyStat[];
}

interface TrafficUserCardProps {
  user: UserTrafficStat;
  period: 'day' | 'week' | 'month' | '30days';
  isExpanded: boolean;
  onToggle: () => void;
  onUserClick?: (userId: number) => void;
  onKeyClick?: (keyId: number) => void;
}

const TrafficUserCard: React.FC<TrafficUserCardProps> = ({ 
  user, 
  period, 
  isExpanded, 
  onToggle,
  onUserClick,
  onKeyClick
}) => {
  const [keysData, setKeysData] = useState<UserKeysResponse | null>(null);
  const [loadingKeys, setLoadingKeys] = useState(false);

  useEffect(() => {
    if (isExpanded && !keysData) {
      loadUserKeys();
    }
  }, [isExpanded]);

  const loadUserKeys = async () => {
    try {
      setLoadingKeys(true);
      const response = await trafficApi.getUserKeys(user.user_id, period);
      setKeysData(response.data);
    } catch (error) {
      console.error('Error loading user keys:', error);
    } finally {
      setLoadingKeys(false);
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (dateString: string | null): string => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const formatUptime = (seconds: number | null): string => {
    if (!seconds) return '-';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}ч ${minutes}м`;
    }
    return `${minutes}м`;
  };

  return (
    <div className={`traffic-user-card ${isExpanded ? 'expanded' : ''}`}>
      <div className="user-card-header">
        <div className="user-card-main" onClick={onToggle}>
          <div className="user-card-avatar">👤</div>
          <div className="user-card-info">
            <div className="user-card-name">
              <span 
                className="user-name-clickable" 
                onClick={(e) => {
                  e.stopPropagation();
                  if (onUserClick) {
                    onUserClick(user.user_id);
                  }
                }}
                title="Показать график трафика этого пользователя"
              >
                {user.user_name}
              </span>
              {user.is_admin && <span className="admin-badge">👑</span>}
              {user.username && <span className="user-username">(@{user.username})</span>}
            </div>
            <div className="user-card-stats">
              <span className="user-keys-count">{user.keys_count} ключей</span>
              {user.active_keys_count > 0 && (
                <span className="user-active-keys">🟢 {user.active_keys_count} активных</span>
              )}
            </div>
          </div>
        </div>
        <div className="user-card-traffic">
          <div className="user-traffic-value">{formatBytes(user.total_traffic)}</div>
        </div>
        <div className="user-card-toggle">
          {isExpanded ? '▲' : '▼'}
        </div>
      </div>

      {isExpanded && (
        <div className="user-card-content">
          {loadingKeys ? (
            <div className="keys-loading">Загрузка ключей...</div>
          ) : keysData ? (
            <>
              <div className="user-summary">
                <div className="summary-item">
                  <span className="summary-label">Входящий:</span>
                  <span className="summary-value">{formatBytes(keysData.summary.total_received)}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Исходящий:</span>
                  <span className="summary-value">{formatBytes(keysData.summary.total_sent)}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Всего:</span>
                  <span className="summary-value">{formatBytes(keysData.summary.total_traffic)}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Активных ключей:</span>
                  <span className="summary-value">
                    {keysData.summary.active_keys_count} из {keysData.summary.total_keys_count}
                  </span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Последнее подключение:</span>
                  <span className="summary-value">{formatDate(keysData.summary.last_connection)}</span>
                </div>
              </div>

              <div className="user-keys">
                <h4>Ключи:</h4>
                {keysData.keys.map((key) => (
                  <div key={key.vpn_key_id} className="key-item">
                    <div className="key-header">
                      <span className="key-icon">🔑</span>
                      <span 
                        className="key-name key-name-clickable" 
                        onClick={(e) => {
                          e.stopPropagation();
                          if (onKeyClick) {
                            onKeyClick(key.vpn_key_id);
                          }
                        }}
                        title="Показать график трафика этого ключа"
                      >
                        {key.key_name}
                      </span>
                      <span className={`key-status ${key.is_active ? 'active' : 'inactive'}`}>
                        {key.is_active ? '🟢 Активен' : '🔴 Неактивен'}
                      </span>
                    </div>
                    <div className="key-stats">
                      <div className="key-stat">
                        <span className="key-stat-label">Входящий:</span>
                        <span className="key-stat-value">{formatBytes(key.received)}</span>
                      </div>
                      <div className="key-stat">
                        <span className="key-stat-label">Исходящий:</span>
                        <span className="key-stat-value">{formatBytes(key.sent)}</span>
                      </div>
                      <div className="key-stat">
                        <span className="key-stat-label">Всего:</span>
                        <span className="key-stat-value">{formatBytes(key.total)}</span>
                      </div>
                      <div className="key-stat">
                        <span className="key-stat-label">Последнее:</span>
                        <span className="key-stat-value">{formatDate(key.last_connection)}</span>
                      </div>
                      {key.connection_ips && key.connection_ips.length > 0 && (
                        <>
                          <div className="key-stat">
                            <span className="key-stat-label">IP:</span>
                            <span className="key-stat-value">
                              {key.connection_ips[0]}
                              {key.connection_ips.length > 1 && ` (+${key.connection_ips.length - 1})`}
                            </span>
                          </div>
                          {key.ip_city && (
                            <div className="key-stat">
                              <span className="key-stat-label">Город:</span>
                              <span className="key-stat-value">{key.ip_city}</span>
                            </div>
                          )}
                          {key.ip_provider && (
                            <div className="key-stat">
                              <span className="key-stat-label">Провайдер:</span>
                              <span className="key-stat-value">{key.ip_provider}</span>
                            </div>
                          )}
                        </>
                      )}
                      {key.is_active && key.uptime_seconds !== null && (
                        <div className="key-stat">
                          <span className="key-stat-label">Время работы:</span>
                          <span className="key-stat-value">{formatUptime(key.uptime_seconds)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="keys-error">Ошибка загрузки ключей</div>
          )}
        </div>
      )}
    </div>
  );
};

export default TrafficUserCard;

