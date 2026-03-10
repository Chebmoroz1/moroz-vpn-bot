import React, { useState, useEffect } from 'react';
import { usersApi } from '../services/api';
import UserEditModal from './UserEditModal';
import './Users.css';

interface User {
  id: number;
  telegram_id: number | null;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  nickname: string | null;
  phone_number: string | null;
  is_active: boolean;
  max_keys: number;
  is_admin: boolean;
  created_at: string;
  vpn_keys_count: number;
  activation_requested?: boolean;
  activation_requested_at?: string | null;
}

const Users: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [showActivationRequests, setShowActivationRequests] = useState(false);

  useEffect(() => {
    loadUsers();
  }, [showActivationRequests]);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const response = showActivationRequests 
        ? await usersApi.getAllWithActivationRequests(0, 1000)
        : await usersApi.getAll(0, 1000);
      setUsers(response.data);
      setError('');
    } catch (err: any) {
      setError('Ошибка при загрузке пользователей');
      console.error('Error loading users:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getUserDisplayName = (user: User) => {
    if (user.nickname) return user.nickname;
    if (user.first_name) {
      return user.last_name ? `${user.first_name} ${user.last_name}` : user.first_name;
    }
    if (user.username) return `@${user.username}`;
    return `User #${user.id}`;
  };

  const handleCreateUser = () => {
    setEditingUser(null);
    setIsModalOpen(true);
  };

  const handleEditUser = (user: User) => {
    setEditingUser(user);
    setIsModalOpen(true);
  };

  const handleSaveUser = async (userData: any) => {
    if (userData.id) {
      await usersApi.update(userData.id, userData);
    } else {
      await usersApi.create(userData);
    }
    loadUsers();
  };

  const handleDeleteUser = async (userId: number) => {
    if (!window.confirm('Вы уверены, что хотите удалить этого пользователя? Все его ключи также будут удалены. Это действие необратимо!')) {
      return;
    }

    try {
      await usersApi.delete(userId);
      loadUsers();
    } catch (err: any) {
      alert('Ошибка при удалении пользователя: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleActivateUser = async (userId: number) => {
    try {
      await usersApi.activate(userId);
      alert('Пользователь активирован');
      // Если мы в режиме просмотра запросов, переключаемся на общий список
      if (showActivationRequests) {
        setShowActivationRequests(false);
      }
      loadUsers();
    } catch (err: any) {
      alert('Ошибка при активации пользователя: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleRejectActivation = async (userId: number) => {
    if (!window.confirm('Отклонить запрос на активацию?')) {
      return;
    }

    try {
      await usersApi.rejectActivation(userId);
      alert('Запрос на активацию отклонен');
      // Обновляем список запросов
      loadUsers();
    } catch (err: any) {
      alert('Ошибка при отклонении запроса: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleExportCSV = async () => {
    try {
      const response = await usersApi.exportCsv();
      const blob = new Blob([response.data], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `users_export_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      alert('Ошибка при экспорте: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleImportCSV = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const response = await usersApi.importCsv(file);
      alert(`Успешно импортировано: ${response.data.imported} пользователей, обновлено: ${response.data.updated}`);
      if (response.data.errors && response.data.errors.length > 0) {
        console.error('Ошибки импорта:', response.data.errors);
        alert('Некоторые строки не были импортированы. Проверьте консоль для деталей.');
      }
      loadUsers();
    } catch (err: any) {
      alert('Ошибка при импорте: ' + (err.response?.data?.detail || err.message));
    } finally {
      // Сбрасываем input
      event.target.value = '';
    }
  };

  if (loading) {
    return <div className="users-loading">Загрузка пользователей...</div>;
  }

  if (error) {
    return <div className="users-error">{error}</div>;
  }

  return (
    <div className="users">
      <div className="users-header">
        <h1>{showActivationRequests ? 'Запросы на активацию' : 'Пользователи'}</h1>
        <div className="users-actions">
          {!showActivationRequests && (
            <>
              <button onClick={handleCreateUser} className="btn-create">
                ➕ Создать пользователя
              </button>
              <button onClick={handleExportCSV} className="btn-export">
                📥 Экспорт CSV
              </button>
              <label className="btn-import">
                📤 Импорт CSV
                <input
                  type="file"
                  accept=".csv"
                  onChange={handleImportCSV}
                  style={{ display: 'none' }}
                />
              </label>
            </>
          )}
          <button 
            onClick={() => {
              setShowActivationRequests(!showActivationRequests);
              // loadUsers будет вызван автоматически через useEffect
            }} 
            className={showActivationRequests ? "refresh-btn" : "btn-export"}
          >
            {showActivationRequests ? '📋 Все пользователи' : '🔓 Запросы на активацию'}
          </button>
          <button onClick={loadUsers} className="refresh-btn">
            🔄 Обновить
          </button>
        </div>
      </div>

      <div className="users-table-container">
        <table className="users-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Имя</th>
              <th>Telegram ID</th>
              <th>Username</th>
              <th>Телефон</th>
              <th>Ключей</th>
              <th>Статус</th>
              <th>Дата регистрации</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id} className={!user.is_active ? 'inactive' : ''}>
                <td>{user.id}</td>
                <td>
                  <strong>{getUserDisplayName(user)}</strong>
                  {user.is_admin && <span className="admin-badge">👑</span>}
                </td>
                <td>{user.telegram_id || '-'}</td>
                <td>{user.username ? `@${user.username}` : '-'}</td>
                <td>{user.phone_number || '-'}</td>
                <td>{user.vpn_keys_count}</td>
                <td>
                  <span className={`status-badge ${user.is_active ? 'active' : 'inactive'}`}>
                    {user.is_active ? '✅ Активен' : '❌ Неактивен'}
                  </span>
                </td>
                <td>{formatDate(user.created_at)}</td>
                <td>
                  <div className="action-buttons">
                    {showActivationRequests ? (
                      <>
                        <button
                          onClick={() => handleActivateUser(user.id)}
                          className="btn-activate"
                          title="Активировать"
                        >
                          ✅
                        </button>
                        <button
                          onClick={() => handleRejectActivation(user.id)}
                          className="btn-reject"
                          title="Отказать"
                        >
                          ❌
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => handleEditUser(user)}
                          className="btn-edit"
                          title="Редактировать"
                        >
                          ✏️
                        </button>
                        <button
                          onClick={() => handleDeleteUser(user.id)}
                          className="btn-delete"
                          title="Удалить"
                        >
                          🗑️
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {users.length === 0 && (
        <div className="users-empty">
          {showActivationRequests 
            ? 'Запросы на активацию не найдены. Если вы активировали пользователя через бота, нажмите "🔄 Обновить" или переключитесь на "📋 Все пользователи".'
            : 'Пользователи не найдены'}
        </div>
      )}

      <UserEditModal
        user={editingUser}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSave={handleSaveUser}
      />
    </div>
  );
};

export default Users;

