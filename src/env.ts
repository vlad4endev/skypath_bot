import { z } from "zod";

const envSchema = z.object({
  DATABASE_URL: z.string().min(1),
  BOT_TOKEN: z.string().min(1),
  BOT_USERNAME: z.string().min(1),
  WEBHOOK_URL: z.string().url().optional(),
  PLATEGA_MERCHANT_ID: z.string().min(1),
  PLATEGA_SECRET: z.string().min(1),
  SUB_URL: z.string().url(),
  ADMIN_IDS: z.string().default(""),
  PORT: z.coerce.number().int().positive().default(3000),
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
});

export type Env = z.infer<typeof envSchema> & {
  adminIds: number[];
  isProduction: boolean;
};

function parseAdminIds(raw: string): number[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => Number(s))
    .filter((n) => Number.isFinite(n));
}

export function loadEnv(): Env {
  const parsed = envSchema.parse(process.env);
  return {
    ...parsed,
    adminIds: parseAdminIds(parsed.ADMIN_IDS),
    isProduction: parsed.NODE_ENV === "production",
  };
}
