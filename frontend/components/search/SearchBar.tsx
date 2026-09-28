"use client";

import { useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/utils";

// Task 1.1.1 - search bar (destination, dates, guests).
// Default: goes to /search?destination=...&checkIn=...&checkOut=...&guests=...
// Pass onSearch to handle it yourself instead (e.g. on the results page).

export type SearchValues = {
  destination: string;
  checkIn: string; // YYYY-MM-DD
  checkOut: string; // YYYY-MM-DD
  guests: number;
};

type Errors = Partial<Record<keyof SearchValues, string>>;

type SearchBarProps = {
  defaultValues?: Partial<SearchValues>;
  onSearch?: (values: SearchValues) => void;
  className?: string;
};

// local date as YYYY-MM-DD (en-CA formats that way)
const today = () => new Date().toLocaleDateString("en-CA");
const noopSubscribe = () => () => {};

function validate(v: SearchValues): Errors {
  const e: Errors = {};
  if (!v.destination.trim()) e.destination = "Where are you going?";
  if (!v.checkIn) e.checkIn = "Pick a check-in date.";
  else if (v.checkIn < today()) e.checkIn = "Check-in can't be in the past.";
  if (!v.checkOut) e.checkOut = "Pick a check-out date.";
  else if (v.checkIn && v.checkOut <= v.checkIn) e.checkOut = "Check-out must be after check-in.";
  if (!Number.isInteger(v.guests) || v.guests < 1) e.guests = "At least 1 guest.";
  else if (v.guests > 10) e.guests = "Max 10 guests.";
  return e;
}

export default function SearchBar({ defaultValues, onSearch, className }: SearchBarProps) {
  const router = useRouter();
  const [values, setValues] = useState<SearchValues>({
    destination: defaultValues?.destination ?? "",
    checkIn: defaultValues?.checkIn ?? "",
    checkOut: defaultValues?.checkOut ?? "",
    guests: defaultValues?.guests ?? 2,
  });
  const [errors, setErrors] = useState<Errors>({});
  // Server renders with no min (server clock is UTC); browser fills in the user's local date.
  const minDate = useSyncExternalStore(noopSubscribe, today, () => "");

  function update<K extends keyof SearchValues>(name: K, value: SearchValues[K]) {
    setValues((v) => ({ ...v, [name]: value }));
    if (errors[name]) setErrors((e) => ({ ...e, [name]: undefined }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const clean = { ...values, destination: values.destination.trim() };
    const found = validate(clean);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    if (onSearch) {
      onSearch(clean);
      return;
    }
    const params = new URLSearchParams({
      destination: clean.destination,
      checkIn: clean.checkIn,
      checkOut: clean.checkOut,
      guests: String(clean.guests),
    });
    router.push(`/search?${params.toString()}`);
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      role="search"
      className={cn(
        "grid w-full grid-cols-1 gap-3 rounded-card border border-line bg-surface p-4 text-left shadow-sm sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_0.8fr_auto] lg:items-start",
        className
      )}
    >
      <SearchField id="destination" label="Destination" error={errors.destination} className="sm:col-span-2 lg:col-span-1">
        <Input
          id="destination"
          placeholder="City or hotel name"
          value={values.destination}
          onChange={(e) => update("destination", e.target.value)}
          aria-invalid={!!errors.destination}
          aria-describedby={errors.destination ? "destination-error" : undefined}
        />
      </SearchField>

      <SearchField id="checkIn" label="Check-in" error={errors.checkIn}>
        <Input
          id="checkIn"
          type="date"
          min={minDate || undefined}
          value={values.checkIn}
          onChange={(e) => update("checkIn", e.target.value)}
          aria-invalid={!!errors.checkIn}
          aria-describedby={errors.checkIn ? "checkIn-error" : undefined}
        />
      </SearchField>

      <SearchField id="checkOut" label="Check-out" error={errors.checkOut}>
        <Input
          id="checkOut"
          type="date"
          min={values.checkIn || minDate || undefined}
          value={values.checkOut}
          onChange={(e) => update("checkOut", e.target.value)}
          aria-invalid={!!errors.checkOut}
          aria-describedby={errors.checkOut ? "checkOut-error" : undefined}
        />
      </SearchField>

      <SearchField id="guests" label="Guests" error={errors.guests}>
        <Input
          id="guests"
          type="number"
          inputMode="numeric"
          min={1}
          max={10}
          value={Number.isNaN(values.guests) ? "" : values.guests}
          onChange={(e) => update("guests", e.target.valueAsNumber)}
          aria-invalid={!!errors.guests}
          aria-describedby={errors.guests ? "guests-error" : undefined}
        />
      </SearchField>

      <div className="sm:col-span-2 lg:col-span-1 lg:pt-6">
        <Button type="submit" size="lg" className="w-full lg:w-auto">
          Search
        </Button>
      </div>
    </form>
  );
}

function SearchField({
  id,
  label,
  error,
  className,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={id} className="block text-xs font-medium uppercase tracking-wider text-muted">
        {label}
      </label>
      {children}
      {error && (
        <p id={`${id}-error`} className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}