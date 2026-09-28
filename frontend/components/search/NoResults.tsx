import { Button } from "@/components/ui/Button";

type NoResultsProps = {
  destination?: string;
  checkIn?: string;
  checkOut?: string;
  onChangeSearch?: () => void;
};

export default function NoResults({ destination, checkIn, checkOut, onChangeSearch }: NoResultsProps) {
  const dates = checkIn && checkOut ? ` for ${checkIn} to ${checkOut}` : "";

  return (
    <div
      role="status"
      className="flex flex-col items-center rounded-card border border-dashed border-line-strong bg-surface px-6 py-12 text-center"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="h-10 w-10 text-subtle"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5M8.5 11h5" />
      </svg>

      <h2 className="mt-4 text-lg font-semibold text-ink">No hotels available</h2>
      <p className="mt-1 max-w-sm text-sm text-muted">
        {destination
          ? `We couldn't find open rooms in "${destination}"${dates}.`
          : "We couldn't find any open rooms for this search."}
      </p>

      <ul className="mt-4 space-y-1 text-sm text-muted">
        <li>Check the spelling of the destination</li>
        <li>Try different or shorter dates</li>
        <li>Lower the number of guests</li>
      </ul>

      {onChangeSearch && (
        <Button variant="outline" className="mt-6" onClick={onChangeSearch}>
          Change search
        </Button>
      )}
    </div>
  );
}