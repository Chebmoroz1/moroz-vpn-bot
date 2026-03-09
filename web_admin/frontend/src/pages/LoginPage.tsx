import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { apiRequest } from "../services/api";

export const LoginPage: React.FC = () => {
  const [telegramId, setTelegramId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { setToken } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const res = await apiRequest<{ access_token: string }>("/auth/token", {
        method: "POST",
        body: JSON.stringify({ telegram_id: Number(telegramId) }),
        headers: { "Content-Type": "application/json" },
      });
      setToken(res.access_token);
      navigate("/");
    } catch (err: any) {
      setError(err.message || "Ошибка авторизации");
    }
  };

  return (
    <div style={{ maxWidth: 400, margin: "40px auto", fontFamily: "sans-serif" }}>
      <h2>Вход в веб-панель</h2>
      <p>Введите ваш Telegram ID администратора.</p>
      <form onSubmit={handleSubmit}>
        <input
          type="number"
          value={telegramId}
          onChange={(e) => setTelegramId(e.target.value)}
          placeholder="Telegram ID"
          style={{ width: "100%", padding: 8, marginBottom: 12 }}
        />
        <button type="submit" style={{ padding: "8px 16px" }}>
          Войти
        </button>
      </form>
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
};

