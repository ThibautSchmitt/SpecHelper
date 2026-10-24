public final class InvoicePolicy {
    public static boolean canFinalize(Invoice invoice, BillingConfig config) {
        if (!invoice.open) return false;
        if (invoice.issuedYear < config.enforcementYear) return true;
        return !config.requireApproval || invoice.approved;
    }

    public record BillingConfig(int enforcementYear, boolean requireApproval) {}
    public record Invoice(boolean open, int issuedYear, boolean approved) {}
}
