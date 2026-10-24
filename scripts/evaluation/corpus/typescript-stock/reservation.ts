export type Order = { channel: string; reserved: number; quantity: number };
export type Settings = { requireReservation: boolean };

export function canDispatch(order: Order, settings: Settings): boolean {
  if (order.channel === "digital") return true;
  if (!settings.requireReservation) return true;
  return order.reserved >= order.quantity;
}
