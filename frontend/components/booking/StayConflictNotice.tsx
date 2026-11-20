import Link from "next/link";
import { CalendarX2 } from "lucide-react";
import { cn } from "@/lib/utils";

// Task 2.4.3 - message + link when a new booking overlaps a stay at another hotel.

export type StayConflict = {
  reservationId: string;
  hotelId: string;
  hotelName: string;
  checkIn: string;
  checkOut: string;
  message: string;
};

/** Returns the conflict if this error body is an overlapping-stay 409, otherwise null. */
export function getStayConflict(body: unknown): StayConflict | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (!Array.isArray(detail)) return null;
  const item = detail.find((d) => d?.type === "overlapping_stay");
  const ctx = item?.ctx;
  if (!ctx?.reservation_id) return null;
  return {
    reservationId: String(ctx.reservation_id),
    hotelId: String(ctx.hotel_id ?? ""),
    hotelName: String(ctx.hotel_name ?? "another hotel"),
    checkIn: String(ctx.check_in ?? ""),
    checkOut: String(ctx.check_out ?? ""),
    message: typeof item.msg === "string" ? item.msg : "",
  };
}

function fmt(value: string) {
  const d = new Date(`${value}T00:00:00`);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function StayConflictNotice({ conflict, className }: { conflict: StayConflict; className?: string }) {
  return (
    <div role="alert" className={cn("space-y-3 rounded-control border border-danger/20 bg-danger-soft p-4", className)}>
      <div className="flex items-start gap-3">
        <CalendarX2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-danger" />
        <div className="space-y-1 text-sm">
          <p className="font-semibold text-ink">You already have a stay on these nights</p>
          <p className="text-muted">
            {conflict.message ||
              `You're booked at ${conflict.hotelName} from ${fmt(conflict.checkIn)} to ${fmt(conflict.checkOut)}.`}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 pl-8">
        <Link
          href={`/bookings?highlight=${encodeURIComponent(conflict.reservationId)}`}
          className="inline-flex h-9 items-center rounded-control bg-ink px-3 text-sm font-semibold text-white hover:opacity-90"
        >
          View that booking
        </Link>
        {conflict.hotelId && (
          <Link
            href={`/hotels/${conflict.hotelId}`}
            className="inline-flex h-9 items-center rounded-control border border-line-strong bg-surface px-3 text-sm font-medium text-ink hover:bg-surface-muted"
          >
            {conflict.hotelName}
          </Link>
        )}
      </div>
    </div>
  );
}