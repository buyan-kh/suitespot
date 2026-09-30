import * as React from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";

export interface Property {
  id: string;
  title: string;
  location: string;
  pricePerNight: number;
  rating: number;
  imageUrl?: string;
}

interface ResultsListProps {
  properties: Property[];
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function ResultsList({
  properties,
  currentPage,
  totalPages,
  onPageChange,
}: ResultsListProps) {
  if (properties.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="text-stone-500 text-sm">No properties found matching your criteria.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Property Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {properties.map((property) => (
          <Link key={property.id} href={`/properties/${property.id}`} className="group">
            <Card className="overflow-hidden border-stone-200/80 bg-white hover:border-stone-300 transition-all">
              {/* Visual Placeholder Box matching Japandi tone */}
              <div className="relative aspect-[4/3] w-full overflow-hidden bg-stone-100 flex items-center justify-center border-b border-stone-200/60 group-hover:bg-stone-200/50 transition-colors">
                <span className="text-xs font-medium text-stone-400 tracking-wider uppercase">
                  {property.location.split(",")[0]} Stay
                </span>
              </div>
              <CardContent className="p-4 space-y-2">
                <div className="flex justify-between items-start">
                  <h3 className="font-medium text-stone-900 text-sm tracking-tight line-clamp-1">
                    {property.title}
                  </h3>
                  <span className="text-xs font-medium text-stone-700 flex items-center gap-1">
                    ★ {property.rating.toFixed(1)}
                  </span>
                </div>
                <p className="text-xs text-stone-500">{property.location}</p>
                <div className="pt-2 flex items-baseline justify-between">
                  <p className="text-sm font-semibold text-stone-900">
                    ${property.pricePerNight} <span className="text-xs font-normal text-stone-500">/ night</span>
                  </p>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center space-x-2 pt-4 border-t border-stone-200">
          <Button
            variant="outline"
            size="sm"
            disabled={currentPage <= 1}
            onClick={() => onPageChange(currentPage - 1)}
            className="border-stone-300 text-stone-700 disabled:opacity-40"
          >
            Previous
          </Button>

          <div className="flex items-center space-x-1 px-2 text-xs font-medium text-stone-600">
            <span>Page {currentPage} of {totalPages}</span>
          </div>

          <Button
            variant="outline"
            size="sm"
            disabled={currentPage >= totalPages}
            onClick={() => onPageChange(currentPage + 1)}
            className="border-stone-300 text-stone-700 disabled:opacity-40"
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}