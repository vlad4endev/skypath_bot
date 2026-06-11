export const PRICES: Record<number, number> = {
  1: 250,
  2: 500,
  3: 750,
  6: 1250,
};

export const AVAILABLE_MONTHS = [1, 2, 3, 6] as const;

export type PlanMonths = (typeof AVAILABLE_MONTHS)[number];

export function getPrice(months: number): number | undefined {
  return PRICES[months];
}

export function formatPrice(months: number): string {
  const price = PRICES[months];
  if (price === undefined) {
    return `${months} мес.`;
  }
  return `${months} мес — ${price}₽`;
}
