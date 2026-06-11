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

async function getSessionCookie(server: Server): Promise<string> {
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

function buildClientSettings(
  server: Server,
  client: {
    id: string;
    email: string;
    subId: string;
    totalGb: number;
    expiryTime: number;
    enable: boolean;
  },
): { id: number; settings: string } {
  const totalBytes = client.totalGb > 0 ? client.totalGb * 1024 ** 3 : 0;
  return {
    id: server.inboundId,
    settings: JSON.stringify({
      clients: [
        {
          id: client.id,
          email: client.email,
          enable: client.enable,
          subId: client.subId,
          totalGB: totalBytes,
          expiryTime: client.expiryTime,
          limitIp: 5,
          flow: "xtls-rprx-vision",
          reset: 0,
        },
      ],
    }),
  };
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
    const payload = buildClientSettings(server, {
      id: uuid,
      email,
      subId,
      totalGb,
      expiryTime,
      enable: true,
    });

    const resp = await fetch(`${baseUrl(server)}/panel/api/inbounds/addClient`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Cookie: cookie,
      },
      body: JSON.stringify(payload),
    });

    const data = (await resp.json()) as { success?: boolean; msg?: string };
    if (!resp.ok || !data.success) {
      throw new Error(data.msg ?? `addClient HTTP ${resp.status}`);
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
    const payload = buildClientSettings(server, {
      id: uuid,
      email,
      subId,
      totalGb,
      expiryTime,
      enable,
    });

    const resp = await fetch(
      `${baseUrl(server)}/panel/api/inbounds/updateClient/${uuid}`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          Cookie: cookie,
        },
        body: JSON.stringify(payload),
      },
    );

    const data = (await resp.json()) as { success?: boolean; msg?: string };
    if (!resp.ok || !data.success) {
      throw new Error(data.msg ?? `updateClient HTTP ${resp.status}`);
    }
  });
}

export async function disableClient(server: Server, uuid: string, email: string, subId: string): Promise<void> {
  await updateClient(server, uuid, email, subId, 0, 0, false);
}
