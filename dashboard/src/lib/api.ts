export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export async function fetchApi(endpoint: string, options: RequestInit = {}) {
  // Only run on client side
  if (typeof window === "undefined") {
    throw new Error("fetchApi should only be called on the client side");
  }

  const token = localStorage.getItem("access_token");
  
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    // Check if it's a 401 Unauthorized, maybe handle logout
    if (res.status === 401) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("user_role");
      document.cookie = "access_token=; Max-Age=0; path=/";
      window.location.href = "/login";
    }
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `API request failed with status ${res.status}`);
  }

  return res.json();
}
