import { cn } from "@/lib/utils";

// Task 4.2.2 - status badge on each booking card.
// Status values come from GET /me/reservations (4.1.1).

export type BookingStatus = "awaiting_payment" | "confirmed" | "completed" | "cancelled";

const STYLES: Record<BookingStatus, { label: string; className: string }> = {
  awaiting_payment: { label: "Awaiting payment", className: "bg-accent/10 text-accent" },
  confirmed: { label: "Upcoming", className: "bg-success-soft text-success" },
  completed: { label: "Completed", className: "bg-surface-muted text-muted" },
  cancelled: { label: "Cancelled", className: "bg-danger-soft text-danger" },
};

export default function StatusBadge({ status, className }: { status: BookingStatus; className?: string }) {
  const style = STYLES[status] ?? STYLES.completed;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap",
        style.className,
        className
      )}
    >
      {style.label}
    </span>
  );
}