import React, { useState, useEffect } from 'react';
import { trafficApi } from '../services/api';
import TrafficUserCard from './TrafficUserCard';
import './TrafficUsersList.css';
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

interface PaginatedUsersResponse {
  users: UserTrafficStat[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

interface TrafficUsersListProps {
  period: 'day' | 'week' | 'month' | '30days';
  onPeriodChange: (period: 'day' | 'week' | 'month' | '30days') => void;
  onUserClick?: (userId: number) => void;
  onKeyClick?: (keyId: number) => void;
}

const TrafficUsersList: React.FC<TrafficUsersListProps> = ({ 
  period, 
  onPeriodChange,
  onUserClick,
  onKeyClick
}) => {
  const [users, setUsers] = useState<UserTrafficStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [expandedUsers, setExpandedUsers] = useState<Set<number>>(new Set());

  useEffect(() => {
    loadUsers();
  }, [period, search, page]);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const response = await trafficApi.getUsers({
        period,
        search: search || undefined,
        sort: 'traffic_desc',
        page,
        limit: 20,
      });
      const data: PaginatedUsersResponse = response.data;
      setUsers(data.users || []);
      setTotalPages(data.total_pages || 1);
    } catch (error: any) {
      console.error('Error loading users:', error);
      setUsers([]);
      setTotalPages(1);
    } finally {
      setLoading(false);
    }
  };

  const handleUserClick = (userId: number) => {
    const newExpanded = new Set(expandedUsers);
    if (newExpanded.has(userId)) {
      newExpanded.delete(userId);
    } else {
      newExpanded.add(userId);
    }
    setExpandedUsers(newExpanded);
  };

  const handleExpandAll = () => {
    if (expandedUsers.size === users.length) {
      setExpandedUsers(new Set());
    } else {
      setExpandedUsers(new Set(users.map(u => u.user_id)));
    }
  };

  if (loading && users.length === 0) {
    return <div className="traffic-users-loading">Загрузка пользователей...</div>;
  }

  return (
    <div className="traffic-users-list">
      <div className="users-list-header">
        <h2>Пользователи (ранжированы по трафику)</h2>
        <div className="users-list-controls">
          <div className="period-selector">
            <button
              className={period === 'day' ? 'active' : ''}
              onClick={() => { onPeriodChange('day'); setPage(1); }}
            >
              День
            </button>
            <button
              className={period === 'week' ? 'active' : ''}
              onClick={() => { onPeriodChange('week'); setPage(1); }}
            >
              Неделя
            </button>
            <button
              className={period === 'month' ? 'active' : ''}
              onClick={() => { onPeriodChange('month'); setPage(1); }}
            >
              Месяц
            </button>
            <button
              className={period === '30days' ? 'active' : ''}
              onClick={() => { onPeriodChange('30days'); setPage(1); }}
            >
              30 дней
            </button>
          </div>
          <input
            type="text"
            placeholder="🔍 Поиск пользователей..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="users-search"
          />
          <button onClick={loadUsers} className="refresh-btn">
            🔄 Обновить
          </button>
          <button onClick={handleExpandAll} className="expand-all-btn">
            {expandedUsers.size === users.length ? 'Свернуть все' : 'Развернуть все'}
          </button>
        </div>
      </div>

      <div className="users-list">
        {users.map((user) => (
          <TrafficUserCard
            key={user.user_id}
            user={user}
            period={period}
            isExpanded={expandedUsers.has(user.user_id)}
            onToggle={() => handleUserClick(user.user_id)}
            onUserClick={onUserClick}
            onKeyClick={onKeyClick}
          />
        ))}
      </div>

      {users.length === 0 && !loading && (
        <div className="users-empty">Пользователи не найдены</div>
      )}

      {totalPages > 1 && (
        <div className="users-pagination">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            ◀️ Предыдущая
          </button>
          <span>Страница {page} из {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            Следующая ▶️
          </button>
        </div>
      )}
    </div>
  );
};

export default TrafficUsersList;

