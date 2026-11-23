import Link from "next/link";
import { cn } from "@/lib/utils";
import { BedDouble, CalendarDays, ImageOff, Users } from "lucide-react";
import { Button } from "@/components/ui/Button";
import StatusBadge, { type BookingStatus } from "@/components/bookings/StatusBadge";

// Task 4.2.1 - one booking on the My Bookings page.
// Task 4.3.1 - Modify + Cancel action buttons.
// Task 4.3.2 - `highlighted` outlines the booking that was just changed or cancelled.
// Data: a card from GET /me/reservations (4.1.1).
export type BookingCardData = {
  id: string;
  status: BookingStatus;
  hotel: {
    id: string;
    name: string;
    city: string;
    image: { alt?: string; sizes?: { thumb?: string } } | null;
  };
  room: { id: string; room_type: string; room_number: string };
  check_in: string;
  check_out: string;
  nights: number;
  num_guests: number;
  total_price: number;
  amount_paid: number;
  hold_expires_at: string | null;
};

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

function formatDate(value: string) {
  const d = new Date(`${value}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}

const titleCase = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export default function BookingCard({
  booking,
  onCancel,
  onModify,
  highlighted = false,
}: {
  booking: BookingCardData;
  onCancel?: (booking: BookingCardData) => void;
  onModify?: (booking: BookingCardData) => void;
  highlighted?: boolean;
}) {
  const { hotel, room, status } = booking;
  const photo = hotel.image?.sizes?.thumb;

  return (
    <article
      id={`booking-${booking.id}`}
      className={cn(
        "flex scroll-mt-6 flex-col overflow-hidden rounded-card border bg-surface shadow-sm transition-shadow sm:flex-row",
        highlighted ? "border-accent ring-2 ring-accent/30" : "border-line"
      )}
    >
      <div className="h-40 w-full shrink-0 bg-surface-muted sm:h-auto sm:w-48">
        {photo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={photo} alt={hotel.image?.alt || hotel.name} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-subtle">
            <ImageOff aria-hidden="true" className="h-6 w-6" />
          </div>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-lg font-bold text-ink">{hotel.name}</h3>
            <p className="text-sm text-muted">{hotel.city}</p>
          </div>
          <StatusBadge status={status} />
        </div>

        <ul className="grid gap-2 text-sm text-ink sm:grid-cols-2">
          <li className="flex items-center gap-2 sm:col-span-2">
            <CalendarDays aria-hidden="true" className="h-4 w-4 shrink-0 text-muted" />
            <span>
              {formatDate(booking.check_in)} – {formatDate(booking.check_out)}
              <span className="text-muted"> · {booking.nights} {booking.nights === 1 ? "night" : "nights"}</span>
            </span>
          </li>
          <li className="flex items-center gap-2">
            <BedDouble aria-hidden="true" className="h-4 w-4 shrink-0 text-muted" />
            {titleCase(room.room_type)} · Room {room.room_number}
          </li>
          <li className="flex items-center gap-2">
            <Users aria-hidden="true" className="h-4 w-4 shrink-0 text-muted" />
            {booking.num_guests} {booking.num_guests === 1 ? "guest" : "guests"}
          </li>
        </ul>

        <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
          <div>
            <p className="text-xs text-muted">{status === "awaiting_payment" ? "Total due" : "Total"}</p>
            <p className="text-lg font-bold text-ink">{money.format(booking.total_price)}</p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Link
              href={`/hotels/${hotel.id}`}
              className="inline-flex h-10 items-center rounded-control border border-line-strong bg-surface px-4 text-sm font-medium text-ink hover:bg-surface-muted"
            >
              View hotel
            </Link>
            {status === "awaiting_payment" && (
              <Link
                href={`/checkout?reservationId=${encodeURIComponent(booking.id)}`}
                className="inline-flex h-10 items-center rounded-control bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-hover"
              >
                Complete payment
              </Link>
            )}
            {(status === "confirmed" || status === "awaiting_payment") && onModify && (
              <Button variant="outline" onClick={() => onModify(booking)}>
                Modify
              </Button>
            )}
            {status === "confirmed" && onCancel && (
              <Button variant="destructive" onClick={() => onCancel(booking)}>
                Cancel
              </Button>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}