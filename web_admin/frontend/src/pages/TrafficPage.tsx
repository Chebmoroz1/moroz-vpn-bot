import React, { useEffect, useState } from "react";
import { useApi } from "../services/api";

type Point = {
  timestamp: string;
  bytes_received: number;
  bytes_sent: number;
};

export const TrafficPage: React.FC = () => {
  const api = useApi();
  const [points, setPoints] = useState<Point[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState("day");

  useEffect(() => {
    (async () => {
      try {
        const data = await api.get<Point[]>(`/traffic/chart?period=${period}`);
        setPoints(data);
      } catch (err: any) {
        setError(err.message || "Ошибка загрузки трафика");
      }
    })();
  }, [period]);

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h2>Трафик</h2>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <label>
        Период:{" "}
        <select value={period} onChange={(e) => setPeriod(e.target.value)}>
          <option value="6hours">6 часов</option>
          <option value="day">Сутки</option>
          <option value="week">Неделя</option>
          <option value="month">Месяц</option>
        </select>
      </label>
      <ul>
        {points.map((p) => (
          <li key={p.timestamp}>
            {new Date(p.timestamp).toLocaleString()}: RX={p.bytes_received} /
            TX={p.bytes_sent}
          </li>
        ))}
      </ul>
    </div>
  );
};

