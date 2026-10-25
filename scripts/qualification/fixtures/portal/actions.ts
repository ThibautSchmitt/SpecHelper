// Fictional portal checks; backend routes remain separate authorization boundaries.
export function showCancel(contract: { status: string }, allowActive: boolean): boolean {
  return contract.status === "draft" || (allowActive && contract.status === "active");
}

export function showRefund(invoice: { status: string }): boolean {
  return invoice.status === "paid";
}
