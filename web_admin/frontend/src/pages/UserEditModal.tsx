import React, { useState, useEffect } from 'react';
import './UserEditModal.css';

interface UserFormData {
  id?: number;
  telegram_id?: number | null;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  nickname?: string | null;
  phone_number?: string | null;
  is_active?: boolean;
  max_keys?: number;
  is_admin?: boolean;
}

interface UserEditModalProps {
  user: UserFormData | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (user: UserFormData) => Promise<void>;
}

const UserEditModal: React.FC<UserEditModalProps> = ({ user, isOpen, onClose, onSave }) => {
  const [formData, setFormData] = useState<UserFormData>({
    telegram_id: null,
    username: null,
    first_name: null,
    last_name: null,
    nickname: null,
    phone_number: null,
    is_active: true,
    max_keys: 1,
    is_admin: false,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    if (user) {
      setFormData(user);
    } else {
      setFormData({
        telegram_id: null,
        username: null,
        first_name: null,
        last_name: null,
        nickname: null,
        phone_number: null,
        is_active: true,
        max_keys: 1,
        is_admin: false,
      });
    }
    setError('');
  }, [user, isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    // Валидация: для создания нового пользователя требуется хотя бы одно из полей
    if (!user) {
      if (!formData.telegram_id && !formData.phone_number && !formData.username) {
        setError('Необходимо заполнить хотя бы одно из полей: Telegram ID, Телефон или Username');
        return;
      }
    }
    
    setLoading(true);

    try {
      await onSave(formData);
      onClose();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка при сохранении пользователя');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{user ? 'Редактировать пользователя' : 'Создать пользователя'}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Telegram ID</label>
            <input
              type="number"
              value={formData.telegram_id || ''}
              onChange={(e) => setFormData({ ...formData, telegram_id: e.target.value ? parseInt(e.target.value) : null })}
              placeholder="123456789"
            />
          </div>

          <div className="form-group">
            <label>Телефон</label>
            <input
              type="text"
              value={formData.phone_number || ''}
              onChange={(e) => setFormData({ ...formData, phone_number: e.target.value || null })}
              placeholder="+79001234567"
            />
          </div>

          <div className="form-group">
            <label>Username</label>
            <input
              type="text"
              value={formData.username || ''}
              onChange={(e) => setFormData({ ...formData, username: e.target.value || null })}
              placeholder="username"
            />
          </div>

          <div className="form-group">
            <label>Имя</label>
            <input
              type="text"
              value={formData.first_name || ''}
              onChange={(e) => setFormData({ ...formData, first_name: e.target.value || null })}
              placeholder="Имя"
            />
          </div>

          <div className="form-group">
            <label>Фамилия</label>
            <input
              type="text"
              value={formData.last_name || ''}
              onChange={(e) => setFormData({ ...formData, last_name: e.target.value || null })}
              placeholder="Фамилия"
            />
          </div>

          <div className="form-group">
            <label>Никнейм (для отображения в боте)</label>
            <input
              type="text"
              value={formData.nickname || ''}
              onChange={(e) => setFormData({ ...formData, nickname: e.target.value || null })}
              placeholder="Никнейм"
            />
          </div>

          <div className="form-group">
            <label>Максимум ключей</label>
            <input
              type="number"
              min="1"
              value={formData.max_keys}
              onChange={(e) => setFormData({ ...formData, max_keys: parseInt(e.target.value) || 1 })}
            />
          </div>

          <div className="form-group checkbox-group">
            <label>
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              />
              Активен
            </label>
          </div>

          {user && (
            <div className="form-group checkbox-group">
              <label>
                <input
                  type="checkbox"
                  checked={formData.is_admin}
                  onChange={(e) => setFormData({ ...formData, is_admin: e.target.checked })}
                />
                Администратор
              </label>
            </div>
          )}

          {error && <div className="form-error">{error}</div>}

          <div className="form-actions">
            <button type="button" onClick={onClose} disabled={loading}>
              Отмена
            </button>
            <button type="submit" disabled={loading}>
              {loading ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default UserEditModal;

