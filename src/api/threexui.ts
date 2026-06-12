import { createHash, randomBytes } from "node:crypto";
import { v4 as uuidv4 } from "uuid";
import type { Server } from "@prisma/client";

const SESSION_TTL_MS = 12 * 60 * 60 * 1000;
const MAX_RETRIES = 3;

interface SessionCache {
  cookie: string;
  expiresAt: number;
}

const sessionCache = new Map<number, SessionCache>();

function baseUrl(server: Server): string {
  return `${server.baseUrl.replace(/\/$/, "")}${server.adminPath.replace(/\/$/, "")}`;
}

function authHeaders(server: Server, cookie = ""): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  const token = process.env.XUI_API_TOKEN?.trim();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  } else if (cookie) {
    headers.Cookie = cookie;
  }
  return headers;
}

async function getSessionCookie(server: Server): Promise<string> {
  if (process.env.XUI_API_TOKEN?.trim()) {
    return "";
  }

  const cached = sessionCache.get(server.id);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.cookie;
  }

  const resp = await fetch(`${baseUrl(server)}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: server.username,
      password: server.password,
    }),
  });

  if (!resp.ok) {
    throw new Error(`3x-ui login failed: HTTP ${resp.status}`);
  }

  const data = (await resp.json()) as { success?: boolean; msg?: string };
  if (data.success === false) {
    throw new Error(data.msg ?? "3x-ui login failed");
  }

  const setCookie = resp.headers.get("set-cookie");
  const cookie = setCookie?.split(";")[0] ?? "";
  if (!cookie) {
    throw new Error("3x-ui login: empty session cookie");
  }

  sessionCache.set(server.id, {
    cookie,
    expiresAt: Date.now() + SESSION_TTL_MS,
  });

  return cookie;
}

async function withRetry<T>(label: string, fn: () => Promise<T>): Promise<T> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (attempt < MAX_RETRIES) {
        await new Promise((r) => setTimeout(r, 1500 * attempt));
      }
    }
  }
  throw new Error(`3x-ui ${label} failed after ${MAX_RETRIES} attempts: ${String(lastError)}`);
}

export function generateClientIds(firstName?: string | null, lastName?: string | null): {
  uuid: string;
  email: string;
  subId: string;
} {
  const clean = `${firstName ?? ""}${lastName ?? ""}`
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
  const suffix = randomBytes(3).toString("hex");
  const email = `${clean || "user"}_${suffix}`;
  const subId = createHash("md5").update(uuidv4()).digest("hex").slice(0, 16);
  return { uuid: uuidv4(), email, subId };
}

function buildClientRecord(
  client: {
    id: string;
    email: string;
    subId: string;
    totalGb: number;
    expiryTime: number;
    enable: boolean;
  },
): Record<string, unknown> {
  const totalBytes = client.totalGb > 0 ? client.totalGb * 1024 ** 3 : 0;
  return {
    id: client.id,
    email: client.email,
    enable: client.enable,
    subId: client.subId,
    totalGB: totalBytes,
    expiryTime: client.expiryTime,
    limitIp: 5,
    flow: "",
    reset: 0,
  };
}

async function addClientLegacy(
  server: Server,
  client: Record<string, unknown>,
  cookie: string,
): Promise<void> {
  const payload = {
    id: server.inboundId,
    settings: JSON.stringify({ clients: [client] }),
  };

  const resp = await fetch(`${baseUrl(server)}/panel/api/inbounds/addClient`, {
    method: "POST",
    headers: authHeaders(server, cookie),
    body: JSON.stringify(payload),
  });

  const data = (await resp.json()) as { success?: boolean; msg?: string };
  if (!resp.ok || !data.success) {
    throw new Error(data.msg ?? `legacy addClient HTTP ${resp.status}`);
  }
}

export async function createClient(
  server: Server,
  email: string,
  uuid: string,
  subId: string,
  totalGb: number,
  expiryTime: number,
): Promise<void> {
  await withRetry("addClient", async () => {
    const cookie = await getSessionCookie(server);
    const client = buildClientRecord({
      id: uuid,
      email,
      subId,
      totalGb,
      expiryTime,
      enable: true,
    });

    const resp = await fetch(`${baseUrl(server)}/panel/api/clients/add`, {
      method: "POST",
      headers: authHeaders(server, cookie),
      body: JSON.stringify({ client, inboundIds: [server.inboundId] }),
    });

    const data = (await resp.json()) as { success?: boolean; msg?: string };
    if (!resp.ok || !data.success) {
      try {
        await addClientLegacy(server, client, cookie);
        return;
      } catch {
        throw new Error(data.msg ?? `clients/add HTTP ${resp.status}`);
      }
    }
  });
}

export async function updateClient(
  server: Server,
  uuid: string,
  email: string,
  subId: string,
  totalGb: number,
  expiryTime: number,
  enable = true,
): Promise<void> {
  await withRetry("updateClient", async () => {
    const cookie = await getSessionCookie(server);
    const client = {
      ...buildClientRecord({
        id: uuid,
        email,
        subId,
        totalGb,
        expiryTime,
        enable,
      }),
      inboundIds: [server.inboundId],
    };

    const resp = await fetch(`${baseUrl(server)}/panel/api/clients/update/${encodeURIComponent(email)}`, {
      method: "POST",
      headers: authHeaders(server, cookie),
      body: JSON.stringify(client),
    });

    const data = (await resp.json()) as { success?: boolean; msg?: string };
    if (!resp.ok || !data.success) {
      const legacyPayload = {
        id: server.inboundId,
        settings: JSON.stringify({ clients: [client] }),
      };
      const legacyResp = await fetch(
        `${baseUrl(server)}/panel/api/inbounds/updateClient/${uuid}`,
        {
          method: "POST",
          headers: authHeaders(server, cookie),
          body: JSON.stringify(legacyPayload),
        },
      );
      const legacyData = (await legacyResp.json()) as { success?: boolean; msg?: string };
      if (!legacyResp.ok || !legacyData.success) {
        throw new Error(legacyData.msg ?? data.msg ?? `updateClient HTTP ${resp.status}`);
      }
    }
  });
}

export async function disableClient(server: Server, uuid: string, email: string, subId: string): Promise<void> {
  await updateClient(server, uuid, email, subId, 0, 0, false);
}

export async function getServerStatus(server: Server): Promise<unknown> {
  return withRetry("server/status", async () => {
    const cookie = await getSessionCookie(server);
    const resp = await fetch(`${baseUrl(server)}/panel/api/server/status`, {
      headers: authHeaders(server, cookie),
    });
    if (!resp.ok) {
      throw new Error(`server/status HTTP ${resp.status}`);
    }
    const data = (await resp.json()) as { success?: boolean; msg?: string; obj?: unknown };
    if (data.success === false) {
      throw new Error(data.msg ?? "server/status failed");
    }
    return data.obj ?? data;
  });
}

export async function getClient(server: Server, email: string): Promise<unknown> {
  return withRetry("clients/get", async () => {
    const cookie = await getSessionCookie(server);
    const resp = await fetch(
      `${baseUrl(server)}/panel/api/clients/get/${encodeURIComponent(email)}`,
      { headers: authHeaders(server, cookie) },
    );
    const data = (await resp.json()) as { success?: boolean; msg?: string; obj?: unknown };
    if (!resp.ok || !data.success) {
      throw new Error(data.msg ?? `clients/get HTTP ${resp.status}`);
    }
    return data.obj ?? data;
  });
}

export async function listInbounds(server: Server): Promise<unknown[]> {
  return withRetry("inbounds/list", async () => {
    const cookie = await getSessionCookie(server);
    const resp = await fetch(`${baseUrl(server)}/panel/api/inbounds/list`, {
      headers: authHeaders(server, cookie),
    });
    const data = (await resp.json()) as { success?: boolean; msg?: string; obj?: unknown[] };
    if (!resp.ok || !data.success) {
      throw new Error(data.msg ?? `inbounds/list HTTP ${resp.status}`);
    }
    return Array.isArray(data.obj) ? data.obj : [];
  });
}
