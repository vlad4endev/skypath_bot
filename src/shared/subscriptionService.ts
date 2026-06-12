import { SubscriptionStatus } from "@prisma/client";
import type { Env } from "../env.js";
import { prisma } from "../db.js";
import {
  createClient,
  disableClient,
  generateClientIds,
  updateClient,
} from "../api/threexui.js";
import { getPrice } from "./pricing.js";

const TRIAL_DAYS = 1;
const TRIAL_GB = 10;

export function buildSubLink(env: Env, subId: string): string {
  return `${env.SUB_URL.replace(/\/$/, "")}/${subId}`;
}

function addMonths(date: Date, months: number): Date {
  const result = new Date(date);
  result.setMonth(result.getMonth() + months);
  return result;
}

function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

async function getActiveServer() {
  const server = await prisma.server.findFirst({
    where: { isActive: true },
    orderBy: { id: "asc" },
  });
  if (!server) {
    throw new Error("Нет активного VPN-сервера");
  }
  return server;
}

export async function getOrCreateUser(telegramId: bigint, profile: {
  username?: string;
  firstName?: string;
  lastName?: string;
}) {
  return prisma.user.upsert({
    where: { telegramId },
    create: {
      telegramId,
      username: profile.username ?? null,
      firstName: profile.firstName ?? null,
      lastName: profile.lastName ?? null,
    },
    update: {
      username: profile.username ?? null,
      firstName: profile.firstName ?? null,
      lastName: profile.lastName ?? null,
    },
  });
}

export async function getLatestSubscription(userId: number) {
  return prisma.subscription.findFirst({
    where: { userId },
    orderBy: { createdAt: "desc" },
    include: { server: true },
  });
}

export async function activateTrial(userId: number, profile: {
  firstName?: string | null;
  lastName?: string | null;
  telegramId?: number;
}) {
  const hadTrial = await prisma.subscription.findFirst({
    where: { userId, status: SubscriptionStatus.TRIAL },
  });
  if (hadTrial) {
    throw new Error("Пробный период уже использован");
  }

  const server = await getActiveServer();
  const { uuid, email, subId } = generateClientIds(
    profile.firstName,
    profile.lastName,
    profile.telegramId,
  );
  const expiresAt = addDays(new Date(), TRIAL_DAYS);
  const expiryTime = expiresAt.getTime();

  await createClient(server, email, uuid, subId, TRIAL_GB, expiryTime);

  return prisma.subscription.create({
    data: {
      userId,
      serverId: server.id,
      status: SubscriptionStatus.TRIAL,
      clientUuid: uuid,
      subId,
      email,
      expiresAt,
      totalGb: TRIAL_GB,
    },
    include: { server: true },
  });
}

export async function activateAfterPayment(paymentId: number, env: Env) {
  const payment = await prisma.payment.findUnique({
    where: { id: paymentId },
    include: {
      user: true,
      subscription: { include: { server: true } },
    },
  });

  if (!payment || payment.status === "PAID") {
    return payment;
  }

  const months = payment.months;
  const now = new Date();
  let subscription = payment.subscription;

  if (!subscription) {
    subscription = await getLatestSubscription(payment.userId);
  }

  const server = subscription?.server ?? (await getActiveServer());

  if (!subscription || !subscription.clientUuid || !subscription.email || !subscription.subId) {
    const { uuid, email, subId } = generateClientIds(
      payment.user.firstName,
      payment.user.lastName,
      Number(payment.user.telegramId),
    );
    const expiresAt = addMonths(now, months);
    await createClient(server, email, uuid, subId, 0, expiresAt.getTime());

    subscription = await prisma.subscription.create({
      data: {
        userId: payment.userId,
        serverId: server.id,
        status: SubscriptionStatus.ACTIVE,
        clientUuid: uuid,
        subId,
        email,
        expiresAt,
        totalGb: 0,
      },
      include: { server: true },
    });
  } else {
    const baseDate =
      subscription.status === SubscriptionStatus.TRIAL ||
      subscription.status === SubscriptionStatus.ACTIVE
        ? subscription.expiresAt && subscription.expiresAt > now
          ? subscription.expiresAt
          : now
        : now;

    const expiresAt = addMonths(baseDate, months);
    await updateClient(
      server,
      subscription.clientUuid,
      subscription.email,
      subscription.subId,
      0,
      expiresAt.getTime(),
      true,
    );

    subscription = await prisma.subscription.update({
      where: { id: subscription.id },
      data: {
        status: SubscriptionStatus.ACTIVE,
        expiresAt,
        totalGb: 0,
        serverId: server.id,
      },
      include: { server: true },
    });
  }

  await prisma.payment.update({
    where: { id: payment.id },
    data: {
      status: "PAID",
      paidAt: now,
      subscriptionId: subscription.id,
    },
  });

  return {
    payment,
    subscription,
    subLink: buildSubLink(env, subscription.subId!),
  };
}

export async function processPaidOrder(orderId: string, env: Env) {
  const payment = await prisma.payment.findUnique({
    where: { orderId },
  });
  if (!payment) {
    throw new Error(`Payment not found: ${orderId}`);
  }
  if (payment.status === "PAID") {
    const sub = payment.subscriptionId
      ? await prisma.subscription.findUnique({ where: { id: payment.subscriptionId } })
      : await getLatestSubscription(payment.userId);
    return {
      alreadyPaid: true as const,
      telegramId: (
        await prisma.user.findUniqueOrThrow({ where: { id: payment.userId } })
      ).telegramId,
      subLink: sub?.subId ? buildSubLink(env, sub.subId) : null,
    };
  }

  const result = await activateAfterPayment(payment.id, env);
  if (!result || !("subLink" in result)) {
    throw new Error("Activation failed");
  }

  const user = await prisma.user.findUniqueOrThrow({ where: { id: payment.userId } });
  return {
    alreadyPaid: false as const,
    telegramId: user.telegramId,
    subLink: result.subLink,
    expiresAt: result.subscription.expiresAt,
  };
}

export async function createPendingPayment(userId: number, months: number) {
  const amount = getPrice(months);
  if (amount === undefined) {
    throw new Error("Неверный период подписки");
  }

  let subscription = await getLatestSubscription(userId);
  if (!subscription) {
    const server = await getActiveServer();
    subscription = await prisma.subscription.create({
      data: {
        userId,
        serverId: server.id,
        status: SubscriptionStatus.AWAITING_PAYMENT,
      },
      include: { server: true },
    });
  }

  return { amount, subscription };
}

export async function expireSubscriptions() {
  const now = new Date();
  const expired = await prisma.subscription.findMany({
    where: {
      status: { in: [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL] },
      expiresAt: { lt: now },
    },
    include: { server: true, user: true },
  });

  for (const sub of expired) {
    if (sub.clientUuid && sub.email && sub.subId) {
      try {
        await disableClient(sub.server, sub.clientUuid, sub.email, sub.subId);
      } catch (error) {
        console.error(`Failed to disable client ${sub.id}:`, error);
      }
    }
    await prisma.subscription.update({
      where: { id: sub.id },
      data: { status: SubscriptionStatus.EXPIRED },
    });
  }

  return expired.length;
}

export async function getExpiringSubscriptions(daysBefore: number) {
  const start = new Date();
  start.setUTCHours(0, 0, 0, 0);
  start.setUTCDate(start.getUTCDate() + daysBefore);

  const end = new Date(start);
  end.setUTCDate(end.getUTCDate() + 1);

  const baseWhere = {
    status: { in: [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL] },
    expiresAt: { gte: start, lt: end },
  };

  if (daysBefore === 3) {
    return prisma.subscription.findMany({
      where: { ...baseWhere, notified3Days: false },
      include: { user: true },
    });
  }

  return prisma.subscription.findMany({
    where: { ...baseWhere, notifiedExpiryDay: false },
    include: { user: true },
  });
}

export async function markNotified(subscriptionId: number, daysBefore: number) {
  const data =
    daysBefore === 3
      ? { notified3Days: true }
      : { notifiedExpiryDay: true };
  await prisma.subscription.update({
    where: { id: subscriptionId },
    data,
  });
}

export function formatStatus(status: SubscriptionStatus): string {
  const map: Record<SubscriptionStatus, string> = {
    TRIAL: "🆓 Пробный период",
    ACTIVE: "✅ Активна",
    EXPIRED: "⏰ Истекла",
    AWAITING_PAYMENT: "💳 Ожидает оплату",
    DISABLED: "🚫 Отключена",
  };
  return map[status];
}
