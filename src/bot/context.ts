import { Context as GrammyContext, SessionFlavor } from "grammy";
import type { Env } from "../env.js";
import type { PlategaClient } from "../api/platega.js";

export interface SessionData {
  pendingOrderId?: string;
}

export type BotContext = GrammyContext & SessionFlavor<SessionData>;

export interface BotDependencies {
  env: Env;
  platega: PlategaClient;
}
