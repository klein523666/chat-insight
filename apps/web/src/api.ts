export type Json = Record<string, unknown> | unknown[];

let csrfToken = "";

export function setCsrf(value: string) {
  csrfToken = value;
}

export function apiErrorMessage(payload: unknown, status: number): string {
  if (typeof payload !== "object" || payload === null || !("detail" in payload)) {
    return `请求失败（${status}）`;
  }
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        typeof item === "object" && item !== null && "msg" in item
          ? String(item.msg)
          : "输入无效",
      )
      .join("；");
  }
  return `请求失败（${status}）`;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (csrfToken && init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(apiErrorMessage(payload, response.status));
  return payload as T;
}

export const mutate = <T>(path: string, method: "POST" | "PUT" | "PATCH" | "DELETE", body?: unknown) =>
  api<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
