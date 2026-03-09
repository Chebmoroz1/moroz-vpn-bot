import React, { useEffect, useState } from "react";
import { useApi } from "../services/api";

type Overview = {
  total_received: number;
  total_sent: number;
  active_connections: number;
  total_keys: number;
};

type GlobalStats = {
  total_users: number;
  active_users: number;
  admins: number;
  total_keys: number;
};

export const DashboardPage: React.FC = () => {
  const api = useApi();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [stats, setStats] = useState<GlobalStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [ov, st] = await Promise.all([
          api.get<Overview>("/traffic/overview"),
          api.get<GlobalStats>("/stats"),
        ]);
        setOverview(ov);
        setStats(st);
      } catch (err: any) {
        setError(err.message || "Ошибка загрузки данных");
      }
    })();
  }, []);

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>MOROZ VPN Dashboard</h1>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        {overview && (
          <div>
            <h3>Трафик</h3>
            <p>Активные подключения: {overview.active_connections}</p>
            <p>Ключей всего: {overview.total_keys}</p>
          </div>
        )}
        {stats && (
          <div>
            <h3>Пользователи</h3>
            <p>Всего: {stats.total_users}</p>
            <p>Активные: {stats.active_users}</p>
            <p>Админы: {stats.admins}</p>
          </div>
        )}
      </div>
    </div>
  );
};

