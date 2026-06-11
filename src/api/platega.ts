import { randomUUID } from "node:crypto";
import type { Env } from "../env.js";

export interface CreateInvoiceParams {
  userId: number;
  months: number;
  amount: number;
  description: string;
  orderId?: string;
}

export interface CreateInvoiceResult {
  orderId: string;
  paymentUrl: string;
}

interface PlategaResponse {
  redirect?: string;
  paymentUrl?: string;
  url?: string;
}

export class PlategaClient {
  private readonly baseUrl = "https://app.platega.io/transaction/process";

  constructor(private readonly env: Env) {}

  async createInvoice(params: CreateInvoiceParams): Promise<CreateInvoiceResult> {
    const orderId = params.orderId ?? randomUUID();

    const resp = await fetch(this.baseUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-MerchantId": this.env.PLATEGA_MERCHANT_ID,
        "X-Secret": this.env.PLATEGA_SECRET,
      },
      body: JSON.stringify({
        paymentMethod: 2,
        paymentDetails: {
          amount: params.amount,
          currency: "RUB",
        },
        description: params.description,
        return: `https://t.me/${this.env.BOT_USERNAME}`,
        payload: {
          userId: params.userId,
          months: params.months,
          orderId,
        },
      }),
    });

    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Platega error HTTP ${resp.status}: ${text}`);
    }

    const data = (await resp.json()) as PlategaResponse;
    const paymentUrl = data.redirect ?? data.paymentUrl ?? data.url;
    if (!paymentUrl) {
      throw new Error("Platega: payment URL missing in response");
    }

    return { orderId, paymentUrl };
  }
}

export interface PlategaWebhookPayload {
  orderId?: string;
  status?: string;
  payload?: {
    userId?: number;
    months?: number;
    orderId?: string;
  };
}

export function parsePlategaWebhook(body: unknown): {
  orderId: string;
  isPaid: boolean;
} | null {
  if (!body || typeof body !== "object") {
    return null;
  }

  const record = body as PlategaWebhookPayload;
  const orderId = record.orderId ?? record.payload?.orderId;
  if (!orderId) {
    return null;
  }

  const status = (record.status ?? "").toLowerCase();
  const isPaid =
    status === "paid" ||
    status === "success" ||
    status === "succeeded" ||
    status === "completed" ||
    status === "confirmed";

  return { orderId, isPaid };
}
