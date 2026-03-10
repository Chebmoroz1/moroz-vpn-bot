import React, { useState, useEffect } from 'react';
import { keysApi, usersApi } from '../services/api';
import './Keys.css';

interface VPNKey {
  id: number;
  user_id: number;
  key_name: string;
  protocol: string;
  created_at: string;
  last_used: string | null;
  expires_at: string | null;
  is_active: boolean;
  client_ip: string | null;
  access_type: string;
  subscription_period_days: number | null;
  purchase_date: string | null;
  is_test: boolean;
}

const Keys: React.FC = () => {
  const [keys, setKeys] = useState<VPNKey[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedUserId, setSelectedUserId] = useState<number | undefined>();

  useEffect(() => {
    loadUsers();
    loadKeys();
  }, [selectedUserId]);

  const loadUsers = async () => {
    try {
      const response = await usersApi.getAll(0, 1000);
      setUsers(response.data);
    } catch (error) {
      console.error('Error loading users:', error);
    }
  };

  const loadKeys = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (selectedUserId) {
        params.user_id = selectedUserId;
      }
      
      const response = await keysApi.getAll(params);
      setKeys(response.data);
    } catch (error) {
      console.error('Error loading keys:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleActivate = async (keyId: number) => {
    try {
      await keysApi.activate(keyId);
      loadKeys();
    } catch (error) {
      console.error('Error activating key:', error);
      alert('Ошибка при активации ключа');
    }
  };

  const handleDeactivate = async (keyId: number) => {
    try {
      await keysApi.deactivate(keyId);
      loadKeys();
    } catch (error) {
      console.error('Error deactivating key:', error);
      alert('Ошибка при деактивации ключа');
    }
  };

  const handleDelete = async (keyId: number) => {
    if (!window.confirm('Вы уверены, что хотите удалить этот ключ?')) {
      return;
    }

    try {
      await keysApi.delete(keyId);
      loadKeys();
    } catch (error) {
      console.error('Error deleting key:', error);
      alert('Ошибка при удалении ключа');
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getUserName = (userId: number) => {
    const user = users.find((u) => u.id === userId);
    if (!user) return `User #${userId}`;
    return user.nickname || user.first_name || user.username || `User #${userId}`;
  };

  if (loading) {
    return <div className="keys-loading">Загрузка ключей...</div>;
  }

  return (
    <div className="keys">
      <div className="keys-header">
        <h1>VPN Ключи</h1>
        <div className="keys-filters">
          <select
            value={selectedUserId || ''}
            onChange={(e) => setSelectedUserId(e.target.value ? parseInt(e.target.value) : undefined)}
            className="user-filter"
          >
            <option value="">Все пользователи</option>
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.nickname || user.first_name || user.username || `User #${user.id}`}
              </option>
            ))}
          </select>
          <button onClick={loadKeys} className="refresh-btn">
            🔄 Обновить
          </button>
        </div>
      </div>

      <div className="keys-table-container">
        <table className="keys-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Имя ключа</th>
              <th>Пользователь</th>
              <th>Протокол</th>
              <th>Тип доступа</th>
              <th>Статус</th>
              <th>Создан</th>
              <th>Истекает</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => (
              <tr key={key.id} className={!key.is_active ? 'inactive' : ''}>
                <td>{key.id}</td>
                <td><strong>{key.key_name}</strong></td>
                <td>{getUserName(key.user_id)}</td>
                <td>{key.protocol}</td>
                <td>
                  <span className={`access-type ${key.access_type}`}>
                    {key.access_type === 'test' && '🧪 Тест'}
                    {key.access_type === 'paid' && '💳 Платный'}
                    {key.access_type === 'free' && '🆓 Бесплатный'}
                    {key.access_type === 'donation' && '💚 Пожертвование'}
                  </span>
                </td>
                <td>
                  <span className={`status-badge ${key.is_active ? 'active' : 'inactive'}`}>
                    {key.is_active ? '✅ Активен' : '❌ Неактивен'}
                  </span>
                </td>
                <td>{formatDate(key.created_at)}</td>
                <td>{formatDate(key.expires_at)}</td>
                <td>
                  <div className="action-buttons">
                    {key.is_active ? (
                      <button
                        onClick={() => handleDeactivate(key.id)}
                        className="btn-deactivate"
                        title="Деактивировать"
                      >
                        ⏸️
                      </button>
                    ) : (
                      <button
                        onClick={() => handleActivate(key.id)}
                        className="btn-activate"
                        title="Активировать"
                      >
                        ▶️
                      </button>
                    )}
                    <button
                      onClick={() => handleDelete(key.id)}
                      className="btn-delete"
                      title="Удалить"
                    >
                      🗑️
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {keys.length === 0 && (
        <div className="keys-empty">Ключи не найдены</div>
      )}
    </div>
  );
};

export default Keys;

