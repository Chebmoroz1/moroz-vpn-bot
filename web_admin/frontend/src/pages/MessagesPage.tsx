import React, { useEffect, useState } from "react";
import { useApi } from "../services/api";

type Message = {
  id: number;
  user_id: number;
  message_type: string;
  message_text: string;
  status: string;
  created_at: string;
};

export const MessagesPage: React.FC = () => {
  const api = useApi();
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.get<Message[]>("/messages");
        setMessages(data);
      } catch (err: any) {
        setError(err.message || "Ошибка загрузки сообщений");
      }
    })();
  }, []);

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h2>Сообщения пользователей</h2>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <ul>
        {messages.map((m) => (
          <li key={m.id}>
            #{m.id} [{m.message_type}] от user {m.user_id} ({m.status}) —{" "}
            {m.message_text}
          </li>
        ))}
      </ul>
    </div>
  );
};

