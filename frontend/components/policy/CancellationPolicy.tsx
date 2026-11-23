import { CalendarCheck, CircleAlert, CircleX } from "lucide-react";
import { cn } from "@/lib/utils";

// Task 3.3.2 - cancellation policy shown on the hotel page and at checkout (US3.3).
// Policy: free more than 7 days before check-in, 50% within 7 days, 100% within 48 hours.
// The fee itself is charged by the backend (3.3.1 Vincent, 3.3.3 David); keep these rules in sync.
//
// Usage:
//   <CancellationPolicy />                                  (hotel page, before dates are picked)
//   <CancellationPolicy checkIn="2026-12-20" total={567} /> (checkout: real dates and amounts)

type Tier = "free" | "half" | "full";

const DAY = 86_400_000;

function parseDate(value: string): number | null {
  const t = Date.parse(`${value}T00:00:00`);
  return Number.isNaN(t) ? null : t;
}

function fmtDate(ms: number) {
  return new Date(ms).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** Which tier applies if the guest cancels at `now`. */
export function currentTier(checkIn: string, now: number = Date.now()): Tier | null {
  const start = parseDate(checkIn);
  if (start === null) return null;
  const left = start - now;
  if (left > 7 * DAY) return "free";
  if (left > 2 * DAY) return "half";
  return "full";
}

export default function CancellationPolicy({
  checkIn,
  total,
  className,
}: {
  checkIn?: string;
  total?: number;
  className?: string;
}) {
  const start = checkIn ? parseDate(checkIn) : null;
  const tier = checkIn ? currentTier(checkIn) : null;
  const money = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
  const fee = (pct: number) => (total !== undefined ? ` (${money((total * pct) / 100)})` : "");

  const rows: { id: Tier; icon: typeof CalendarCheck; title: string; when: string; tone: string }[] = [
    {
      id: "free",
      icon: CalendarCheck,
      title: "Free cancellation",
      when: start ? `Before ${fmtDate(start - 7 * DAY)}` : "More than 7 days before check-in",
      tone: "text-success",
    },
    {
      id: "half",
      icon: CircleAlert,
      title: `50% fee${fee(50)}`,
      when: start ? `${fmtDate(start - 7 * DAY)} – ${fmtDate(start - 2 * DAY)}` : "Within 7 days of check-in",
      tone: "text-accent",
    },
    {
      id: "full",
      icon: CircleX,
      title: `No refund${fee(100)}`,
      when: start ? `From ${fmtDate(start - 2 * DAY)}` : "Within 48 hours of check-in",
      tone: "text-danger",
    },
  ];

  return (
    <section aria-labelledby="policy-title" className={cn("space-y-3", className)}>
      <h2 id="policy-title" className="text-base font-bold text-ink">
        Cancellation policy
      </h2>
      <ol className="space-y-2">
        {rows.map((r) => {
          const Icon = r.icon;
          const isNow = tier === r.id;
          return (
            <li
              key={r.id}
              aria-current={isNow ? "true" : undefined}
              className={cn(
                "flex items-start gap-3 rounded-control border px-3 py-2.5",
                isNow ? "border-ink bg-surface" : "border-line bg-surface"
              )}
            >
              <Icon aria-hidden="true" className={cn("mt-0.5 h-4 w-4 shrink-0", r.tone)} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink">{r.title}</p>
                <p className="text-xs text-muted">{r.when}</p>
              </div>
              {isNow && (
                <span className="shrink-0 rounded-full bg-ink px-2 py-0.5 text-[11px] font-semibold text-white">
                  If you cancel now
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}