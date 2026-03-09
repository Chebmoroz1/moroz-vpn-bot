import { useAuth } from "../contexts/AuthContext";

const API_BASE = "/api";

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null
): Promise<T> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  if (token) {
    // Backend expects token as query param; we also send as header for future extension.
    (headers as any)["X-Auth-Token"] = token;
  }

  const url = `${API_BASE}${path}`;
  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed with status ${res.status}`);
  }
  return (await res.json()) as T;
}

export function useApi() {
  const { token } = useAuth();
  return {
    get: <T,>(path: string) => apiRequest<T>(path, { method: "GET" }, token),
    post: <T,>(path: string, body?: any) =>
      apiRequest<T>(
        path,
        {
          method: "POST",
          body: body ? JSON.stringify(body) : undefined,
        },
        token
      ),
    put: <T,>(path: string, body?: any) =>
      apiRequest<T>(
        path,
        {
          method: "PUT",
          body: body ? JSON.stringify(body) : undefined,
        },
        token
      ),
    del: <T,>(path: string) =>
      apiRequest<T>(path, { method: "DELETE" }, token),
  };
}

