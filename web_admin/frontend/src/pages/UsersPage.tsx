import React, { useEffect, useState } from "react";
import { useApi } from "../services/api";

type User = {
  id: number;
  telegram_id: number | null;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  is_active: boolean;
  max_keys: number;
  is_admin: boolean;
};

export const UsersPage: React.FC = () => {
  const api = useApi();
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.get<User[]>("/users");
        setUsers(data);
      } catch (err: any) {
        setError(err.message || "Ошибка загрузки пользователей");
      }
    })();
  }, []);

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h2>Пользователи</h2>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Telegram</th>
            <th>Имя</th>
            <th>Статус</th>
            <th>Лимит ключей</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.id}</td>
              <td>{u.telegram_id}</td>
              <td>
                {u.first_name} {u.last_name} ({u.username})
              </td>
              <td>{u.is_active ? "✅" : "❌"}</td>
              <td>{u.max_keys}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

