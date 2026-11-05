'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { SlidersHorizontal, ChevronUp, ChevronDown, Star } from 'lucide-react';
import { cn } from '@/lib/utils';

const ROOM_TYPES = [
  { value: '', label: 'Any' },
  { value: 'single', label: 'Single' },
  { value: 'double', label: 'Double' },
  { value: 'suite', label: 'Suite' },
] as const;

const AMENITY_OPTIONS = [
  'Pool',
  'Breakfast included',
  'Spa & wellness',
  'Beach nearby',
  'Free parking',
  'Restaurant',
];

const FILTER_KEYS = ['minPrice', 'maxPrice', 'minStars', 'roomType', 'amenities'] as const;

type Filters = {
  minPrice: string;
  maxPrice: string;
  minStars: string;
  roomType: string;
  amenities: string;
};

type Errors = Partial<Record<'minPrice' | 'maxPrice', string>>;

function validate(f: Filters): Errors {
  const e: Errors = {};
  const min = f.minPrice === '' ? null : Number(f.minPrice);
  const max = f.maxPrice === '' ? null : Number(f.maxPrice);
  if (min !== null && (Number.isNaN(min) || min < 0)) e.minPrice = 'Enter 0 or more.';
  if (max !== null && (Number.isNaN(max) || max < 0)) e.maxPrice = 'Enter 0 or more.';
  if (!e.minPrice && !e.maxPrice && min !== null && max !== null && min > max)
    e.maxPrice = 'Max must be at least the min.';
  return e;
}

type FilterPanelProps = { className?: string };

export default function FilterPanel({ className }: FilterPanelProps) {
  const searchParams = useSearchParams();
  return <FilterForm key={searchParams.toString()} className={className} />;
}

function FilterForm({ className }: FilterPanelProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isFirstRender = useRef(true);

  const [filters, setFilters] = useState<Filters>({
    minPrice: searchParams.get('minPrice') ?? '',
    maxPrice: searchParams.get('maxPrice') ?? '',
    minStars: searchParams.get('minStars') ?? '',
    roomType: searchParams.get('roomType') ?? '',
    amenities: searchParams.get('amenities') ?? '',
  });
  const [errors, setErrors] = useState<Errors>({});

  // Collapsible section toggles
  const [sections, setSections] = useState({
    amenities: true,
    flexibility: true,
    placeType: true,
    rating: true,
  });

  const toggleSection = (key: keyof typeof sections) => {
    setSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const activeCount = FILTER_KEYS.filter((k) => searchParams.get(k)).length;

  function update(name: keyof Filters, value: string) {
    setFilters((f) => ({ ...f, [name]: value }));
    if (name in errors) setErrors((e) => ({ ...e, [name]: undefined }));
  }

  const selectedAmenities = filters.amenities ? filters.amenities.split(',').map(s => s.trim()) : [];

  function handleAmenityToggle(amenity: string) {
    let next: string[];
    if (selectedAmenities.includes(amenity)) {
      next = selectedAmenities.filter((a) => a !== amenity);
    } else {
      next = [...selectedAmenities, amenity];
    }
    update('amenities', next.join(','));
  }

  function pushParams(next: Filters) {
    const params = new URLSearchParams(searchParams.toString());
    for (const key of FILTER_KEYS) {
      const value = next[key].trim();
      if (value) params.set(key, value);
      else params.delete(key);
    }
    params.delete('offset'); // new filters start back on page 1
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  // Task 1.7.1: Debounced auto-refetch when user changes filters (350ms delay)
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }

    const found = validate(filters);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      pushParams(filters);
    }, 350);

    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [filters]);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    const found = validate(filters);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    pushParams(filters);
  }

  function handleClear() {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    const empty: Filters = { minPrice: '', maxPrice: '', minStars: '', roomType: '', amenities: '' };
    setFilters(empty);
    setErrors({});
    pushParams(empty);
  }

  const currentStars = filters.minStars ? Number(filters.minStars) : 0;

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-label="Filter hotels"
      className={cn('space-y-6 rounded-card border border-line bg-surface p-6 text-ink', className)}
    >
      {/* Header & Reset */}
      <div className="flex items-center justify-between border-b border-line pb-4">
        <div>
          <h2 className="text-base font-black uppercase tracking-tight text-ink">Make it yours.</h2>
          {activeCount > 0 ? (
            <button
              type="button"
              onClick={handleClear}
              className="text-xs font-bold text-accent underline underline-offset-2 mt-0.5 cursor-pointer hover:opacity-80"
            >
              Reset all filters ({activeCount})
            </button>
          ) : (
            <p className="text-xs text-muted mt-0.5">Filter your stay</p>
          )}
        </div>
        <SlidersHorizontal className="w-5 h-5 text-muted" />
      </div>

      {/* Nightly Budget Visualizer & Inputs */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-bold text-ink">Your nightly budget</legend>

        <div className="grid grid-cols-2 gap-3 pt-2">
          <div className="space-y-1">
            <label htmlFor="minPrice" className="text-xs text-muted font-medium">
              Min
            </label>
            <Input
              id="minPrice"
              type="number"
              inputMode="numeric"
              min={0}
              placeholder="0"
              value={filters.minPrice}
              onChange={(e) => update('minPrice', e.target.value)}
              aria-invalid={!!errors.minPrice}
            />
            {errors.minPrice && (
              <p id="minPrice-error" className="text-xs text-danger">
                {errors.minPrice}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <label htmlFor="maxPrice" className="text-xs text-muted font-medium">
              Max
            </label>
            <Input
              id="maxPrice"
              type="number"
              inputMode="numeric"
              min={0}
              placeholder="Any"
              value={filters.maxPrice}
              onChange={(e) => update('maxPrice', e.target.value)}
              aria-invalid={!!errors.maxPrice}
            />
            {errors.maxPrice && (
              <p id="maxPrice-error" className="text-xs text-danger">
                {errors.maxPrice}
              </p>
            )}
          </div>
        </div>
      </fieldset>

      <hr className="border-line" />

      {/* Star rating Slider */}
      <fieldset className="space-y-3">
        <div className="flex justify-between items-center">
          <legend className="text-sm font-bold text-ink">Minimum Star Rating</legend>
          <span className="text-xs font-bold text-accent flex items-center gap-1">
            <Star className="w-3.5 h-3.5 fill-accent text-accent" />
            {currentStars === 0 ? 'Any rating' : `${currentStars} Stars & Up`}
          </span>
        </div>
        <input
          type="range"
          min="0"
          max="5"
          step="1"
          value={currentStars}
          onChange={(e) => update('minStars', e.target.value === '0' ? '' : e.target.value)}
          className="w-full accent-accent cursor-pointer h-1.5 bg-line-strong/30 rounded-lg appearance-none"
        />
        <div className="flex justify-between text-[10px] text-muted font-bold px-1">
          <span>Any</span>
          <span>1★</span>
          <span>2★</span>
          <span>3★</span>
          <span>4★</span>
          <span>5★</span>
        </div>
      </fieldset>

      <hr className="border-line" />

      {/* Room type */}
      <fieldset className="space-y-2">
        <legend className="text-sm font-bold text-ink">Room type</legend>
        <div className="flex flex-wrap gap-2">
          {ROOM_TYPES.map((r) => (
            <ChipButton
              key={r.value || 'any'}
              pressed={filters.roomType === r.value}
              onClick={() => update('roomType', r.value)}
            >
              {r.label}
            </ChipButton>
          ))}
        </div>
      </fieldset>

      <hr className="border-line" />

      {/* Interactive Amenities Section */}
      <div className="space-y-3">
        <button
          type="button"
          onClick={() => toggleSection('amenities')}
          className="flex items-center justify-between w-full text-sm font-bold text-ink cursor-pointer"
        >
          <span>Amenities</span>
          {sections.amenities ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {sections.amenities && (
          <div className="space-y-2.5 pt-1">
            {AMENITY_OPTIONS.map((amenity) => {
              const isChecked = selectedAmenities.includes(amenity);
              return (
                <label key={amenity} className="flex items-center justify-between text-xs text-ink cursor-pointer group">
                  <div className="flex items-center gap-2.5">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => handleAmenityToggle(amenity)}
                      className="w-4 h-4 rounded border-line-strong accent-accent cursor-pointer"
                    />
                    <span className="group-hover:text-accent font-medium">{amenity}</span>
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </div>

      <Button type="submit" className="w-full">
        Apply filters
      </Button>
    </form>
  );
}

function ChipButton({
  pressed,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { pressed: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      className={cn(
        'h-9 rounded-control border px-3 text-sm font-medium transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus',
        pressed
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-line-strong bg-surface text-ink hover:bg-surface-muted',
        className
      )}
      {...props}
    />
  );
}