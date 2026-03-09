import React, { useEffect, useState } from "react";
import { useApi } from "../services/api";

type Setting = {
  key: string;
  value: string | null;
  description: string | null;
  is_secret: boolean;
  category: string;
};

type SettingsUpdate = {
  items: Setting[];
};

export const SettingsPage: React.FC = () => {
  const api = useApi();
  const [settings, setSettings] = useState<Setting[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.get<Setting[]>("/settings");
        setSettings(data);
      } catch (err: any) {
        setError(err.message || "Ошибка загрузки настроек");
      }
    })();
  }, []);

  const handleChange = (idx: number, value: string) => {
    setSettings((prev) =>
      prev.map((s, i) => (i === idx ? { ...s, value } : s))
    );
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload: SettingsUpdate = { items: settings };
      await api.put("/settings", payload);
    } catch (err: any) {
      setError(err.message || "Ошибка сохранения настроек");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h2>Настройки</h2>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Ключ</th>
            <th>Значение</th>
            <th>Описание</th>
            <th>Категория</th>
          </tr>
        </thead>
        <tbody>
          {settings.map((s, idx) => (
            <tr key={s.key}>
              <td>{s.key}</td>
              <td>
                <input
                  type="text"
                  value={s.value ?? ""}
                  onChange={(e) => handleChange(idx, e.target.value)}
                />
              </td>
              <td>{s.description}</td>
              <td>{s.category}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={handleSave} disabled={saving}>
        {saving ? "Сохранение..." : "Сохранить"}
      </button>
    </div>
  );
};

