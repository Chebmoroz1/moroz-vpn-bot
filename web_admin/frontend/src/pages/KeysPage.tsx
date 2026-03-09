import React, { useEffect, useState } from "react";
import { useApi } from "../services/api";

type Key = {
  id: number;
  user_id: number;
  key_name: string;
  client_ip: string | null;
  is_active: boolean;
};

export const KeysPage: React.FC = () => {
  const api = useApi();
  const [keys, setKeys] = useState<Key[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const data = await api.get<Key[]>("/keys");
      setKeys(data);
    } catch (err: any) {
      setError(err.message || "Ошибка загрузки ключей");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleDelete = async (id: number) => {
    try {
      await api.del(`/keys/${id}`);
      await load();
    } catch (err: any) {
      setError(err.message || "Ошибка удаления ключа");
    }
  };

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h2>VPN ключи</h2>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>User ID</th>
            <th>Имя</th>
            <th>IP</th>
            <th>Статус</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k.id}>
              <td>{k.id}</td>
              <td>{k.user_id}</td>
              <td>{k.key_name}</td>
              <td>{k.client_ip}</td>
              <td>{k.is_active ? "🟢" : "🔴"}</td>
              <td>
                <button onClick={() => handleDelete(k.id)}>Удалить</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

