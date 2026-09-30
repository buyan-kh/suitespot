"use client";

import { useState } from "react";
import { ResultsList, Property } from "@/components/ResultsList";

const mockProperties: Property[] = [
  {
    id: "1",
    title: "Pacific Haven",
    location: "San Francisco, United States",
    pricePerNight: 280,
    rating: 4.9,
    imageUrl: "https://images",
  },
  {
    id: "2",
    title: "Tuscan Villa",
    location: "Tuscany, Italy",
    pricePerNight: 240,
    rating: 4.8,
    imageUrl: "https://images",
  },
  {
    id: "3",
    title: "Zen Retreat",
    location: "Byron Bay, Australia",
    pricePerNight: 310,
    rating: 5.0,
    imageUrl: "https://images",
  },
];
export default function TestResultsPage() {
  const [currentPage, setCurrentPage] = useState(1);
  const totalPages = 3;

  return (
    <main className="max-w-7xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-semibold text-stone-900 mb-6">Testing Results List Component</h1>
      <ResultsList
        properties={mockProperties}
        currentPage={currentPage}
        totalPages={totalPages}
        onPageChange={(page) => setCurrentPage(page)}
      />
    </main>
  );
}