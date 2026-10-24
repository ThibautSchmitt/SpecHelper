// The historical bulk import stores shipment states without the dispatch predicate.
export function importShipment(row: Record<string, unknown>) {
  return { ...row, state: "dispatched", origin: "legacy_import" };
}
