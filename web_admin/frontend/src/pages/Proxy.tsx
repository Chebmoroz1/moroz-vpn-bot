import React, { useState, useEffect, useCallback } from 'react';
import { proxyApi, ProxyActiveConnection } from '../services/api';
import './Proxy.css';

const Proxy: React.FC = () => {
  const [data, setData] = useState<{ total: number; connections: ProxyActiveConnection[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const res = await proxyApi.getActive();
      setData(res.data);
      setLastUpdate(new Date());
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Ошибка загрузки');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const formatLastUpdate = (date: Date | null): string => {
    if (!date) return '';
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="proxy-page">
      <div className="proxy-header">
        <h1>📡 MTProxy — активные подключения</h1>
        <p className="proxy-subtitle">Текущие TCP-сессии на порт 8444 (Telegram-прокси) с геолокацией</p>
        <div className="proxy-header-actions">
          {lastUpdate && (
            <span className="last-update">Обновлено: {formatLastUpdate(lastUpdate)}</span>
          )}
          <button onClick={loadData} className="refresh-btn" disabled={loading}>
            {loading ? '⏳ Загрузка...' : '🔄 Обновить'}
          </button>
        </div>
      </div>

      {error && (
        <div className="proxy-error">
          ❌ {error}
        </div>
      )}

      {!error && data && (
        <>
          <div className="proxy-summary">
            Всего подключений: <strong>{data.total}</strong>
          </div>
          {data.connections.length === 0 ? (
            <div className="proxy-empty">Нет активных подключений</div>
          ) : (
            <div className="proxy-table-wrap">
              <table className="proxy-table">
                <thead>
                  <tr>
                    <th>IP</th>
                    <th>Город</th>
                    <th>Провайдер</th>
                  </tr>
                </thead>
                <tbody>
                  {data.connections.map((c) => (
                    <tr key={c.ip}>
                      <td className="proxy-ip">{c.ip}</td>
                      <td>{c.city || '—'}</td>
                      <td>{c.provider || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default Proxy;
