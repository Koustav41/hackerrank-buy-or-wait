export const API_BASE = "http://localhost:8000";

export async function safeFetch(path: string, options?: RequestInit) {
  const hosts = ["http://localhost:8000", "http://127.0.0.1:8000"];
  for (const host of hosts) {
    try {
      const res = await fetch(`${host}${path}`, options);
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // try next host
    }
  }
  return null;
}
