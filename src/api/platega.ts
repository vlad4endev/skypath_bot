import { randomUUID } from "node:crypto";
import type { Env } from "../env.js";

export interface CreateInvoiceParams {
  userId: number;
  months: number;
  amount: number;
  description: string;
  orderId?: string;
  subscriptionId?: number;
  plan?: string;
}

export interface CreateInvoiceResult {
  orderId: string;
  transactionId: string;
  paymentUrl: string;
}

const API_BASE = "https://app.platega.io";

interface PlategaCreateResponse {
  transactionId?: string;
  id?: string;
  redirect?: string;
  url?: string;
  paymentUrl?: string;
  status?: string;
}

interface PlategaCallbackPayload {
  id?: string;
  amount?: number;
  currency?: string;
  status?: string;
  paymentMethod?: number;
  payload?: string;
  orderId?: string;
}

function serializePayload(metadata: Record<string, string | number>): string {
  return JSON.stringify(metadata);
}

function parsePayload(raw: unknown): Record<string, unknown> {
  if (typeof raw === "object" && raw !== null) {
    return raw as Record<string, unknown>;
  }
  if (typeof raw === "string" && raw.trim()) {
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (typeof parsed === "object" && parsed !== null) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      return {};
    }
  }
  return {};
}

function extractPaymentUrl(data: PlategaCreateResponse): string | undefined {
  return data.redirect ?? data.url ?? data.paymentUrl;
}

function extractTransactionId(data: PlategaCreateResponse): string | undefined {
  return data.transactionId ?? data.id;
}

export class PlategaClient {
  constructor(private readonly env: Env) {}

  private headers(): Record<string, string> {
    return {
      "Content-Type": "application/json",
      "X-MerchantId": this.env.PLATEGA_MERCHANT_ID,
      "X-Secret": this.env.PLATEGA_SECRET,
    };
  }

  async createInvoice(params: CreateInvoiceParams): Promise<CreateInvoiceResult> {
    const orderId = params.orderId ?? randomUUID();
    const methodRaw = process.env.PLATEGA_PAYMENT_METHOD?.trim();
    const paymentMethod = methodRaw ? Number.parseInt(methodRaw, 10) : NaN;

    const body: Record<string, unknown> = {
      paymentDetails: {
        amount: params.amount,
        currency: "RUB",
      },
      description: params.description,
      return: `https://t.me/${this.env.BOT_USERNAME}`,
      failedUrl: `https://t.me/${this.env.BOT_USERNAME}?start=payment_failed`,
      payload: serializePayload({
        userId: params.userId,
        months: params.months,
        orderId,
        ...(params.subscriptionId ? { subscription_id: params.subscriptionId } : {}),
        ...(params.plan ? { plan: params.plan } : {}),
      }),
    };

    const url =
      Number.isFinite(paymentMethod) && paymentMethod > 0
        ? `${API_BASE}/transaction/process`
        : `${API_BASE}/v2/transaction/process`;

    if (Number.isFinite(paymentMethod) && paymentMethod > 0) {
      body.paymentMethod = paymentMethod;
    }

    const resp = await fetch(url, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Platega error HTTP ${resp.status}: ${text}`);
    }

    const data = (await resp.json()) as PlategaCreateResponse;
    const paymentUrl = extractPaymentUrl(data);
    if (!paymentUrl) {
      throw new Error("Platega: payment URL missing in response");
    }

    const transactionId = extractTransactionId(data) ?? orderId;
    return { orderId, transactionId, paymentUrl };
  }
}

export function verifyPlategaWebhookHeaders(
  headers: Record<string, string | undefined>,
  env: Env,
): boolean {
  const merchant = headers["x-merchantid"] ?? headers["X-MerchantId"];
  const secret = headers["x-secret"] ?? headers["X-Secret"];
  if (!merchant || !secret) {
    return false;
  }
  return merchant === env.PLATEGA_MERCHANT_ID && secret === env.PLATEGA_SECRET;
}

export function parsePlategaWebhook(body: unknown): {
  orderId: string | null;
  transactionId: string | null;
  isPaid: boolean;
  isCancelled: boolean;
} | null {
  if (!body || typeof body !== "object") {
    return null;
  }

  const record = body as PlategaCallbackPayload;
  const payload = parsePayload(record.payload);
  const orderId =
    (typeof record.orderId === "string" ? record.orderId : null) ??
    (typeof payload.orderId === "string" ? payload.orderId : null);
  const transactionId =
    typeof record.id === "string"
      ? record.id
      : typeof (record as { transactionId?: string }).transactionId === "string"
        ? (record as { transactionId: string }).transactionId
        : null;

  if (!orderId && !transactionId) {
    return null;
  }

  const status = (record.status ?? "").toUpperCase();
  const isPaid = status === "CONFIRMED" || status === "PAID" || status === "SUCCESS";
  const isCancelled =
    status === "CANCELED" ||
    status === "CANCELLED" ||
    status === "FAILED" ||
    status === "CHARGEBACKED";

  return { orderId, transactionId, isPaid, isCancelled };
}
