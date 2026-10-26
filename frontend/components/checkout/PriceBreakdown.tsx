import { cn } from "@/lib/utils";

export type PriceLine = { label: string; amount: number };

type PriceBreakdownProps = {
  nightlyRate: number;
  nights: number;
  fees?: PriceLine[];
  taxes?: PriceLine[];
  /** Total from the API. If left out, the lines are added up here. */
  total?: number;
  currency?: string;
  className?: string;
};

// Add in cents so 0.1 + 0.2 style float errors never reach the screen.
const toCents = (n: number) => Math.round(n * 100);

/** Nights between two YYYY-MM-DD dates (0 if invalid or out of order). */
export function nightsBetween(checkIn: string, checkOut: string): number {
  const a = Date.parse(`${checkIn}T00:00:00Z`);
  const b = Date.parse(`${checkOut}T00:00:00Z`);
  if (Number.isNaN(a) || Number.isNaN(b) || b <= a) return 0;
  return Math.round((b - a) / 86_400_000);
}

export default function PriceBreakdown({
  nightlyRate,
  nights,
  fees = [],
  taxes = [],
  total,
  currency = "USD",
  className,
}: PriceBreakdownProps) {
  const money = new Intl.NumberFormat("en-US", { style: "currency", currency });
  const fmt = (cents: number) => money.format(cents / 100);

  const stayCents = toCents(nightlyRate) * nights;
  const lines = [...fees, ...taxes];
  const computedCents = stayCents + lines.reduce((sum, l) => sum + toCents(l.amount), 0);
  const totalCents = total === undefined ? computedCents : toCents(total);

  return (
    <div className={cn("space-y-3 text-sm", className)}>
      <dl className="space-y-2">
        <Row
          label={`${fmt(toCents(nightlyRate))} × ${nights} ${nights === 1 ? "night" : "nights"}`}
          value={fmt(stayCents)}
        />
        {fees.map((f) => (
          <Row key={`fee-${f.label}`} label={f.label} value={fmt(toCents(f.amount))} />
        ))}
        {taxes.map((t) => (
          <Row key={`tax-${t.label}`} label={t.label} value={fmt(toCents(t.amount))} />
        ))}
      </dl>

      <div className="flex items-baseline justify-between border-t border-line pt-3">
        <span className="text-base font-bold text-ink">Total</span>
        <span className="text-lg font-bold text-ink">{fmt(totalCents)}</span>
      </div>

      {fees.length === 0 && taxes.length === 0 && (
        <p className="text-xs text-muted">Taxes and fees are shown at checkout.</p>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium text-ink whitespace-nowrap">{value}</dd>
    </div>
  );
}