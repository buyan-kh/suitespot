import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";

export default function Home() {
  const featuredStays = [
    { id: 1, title: "ENGR 337A", location: "San Jose, CA", price: "$320 / night" },
    { id: 2, title: "Small Tent", location: "San Francisco, CA", price: "$840 / night" },
    { id: 3, title: "Tahoetel", location: "Lake Tahoe, NV", price: "$410 / night" },
  ];

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
      {/* Hero Section */}
      <div className="max-w-3xl text-center space-y-6 mb-16">
        <h1 className="text-4xl sm:text-6xl font-semibold tracking-tight text-stone-900">
          Find your next stay with <span className="text-stone-600 font-normal underline decoration-stone-300 decoration-1 underline-offset-8">LikeHome</span>
        </h1>

        {/* Search Bar Widget */}
        <div className="mt-8 bg-white p-4 rounded-2xl shadow-sm border border-stone-200/80 flex flex-col sm:flex-row gap-3">
          <div className="flex-1 text-left px-2">
            <label className="block text-xs font-medium text-stone-400 uppercase tracking-wider mb-1">
              Location
            </label>
            <Input placeholder="Where are you going?" className="border-none shadow-none px-0 focus-visible:ring-0 text-stone-900 placeholder:text-stone-300" />
          </div>
          <div className="flex items-end">
            <Button className="w-full sm:w-auto h-12 px-8 rounded-xl font-medium">Search</Button>
          </div>
        </div>
      </div>

      {/* Featured Section Using Cards */}
      <div className="w-full space-y-6">
        <h2 className="text-2xl font-semibold tracking-tight text-stone-900">Featured Destinations</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {featuredStays.map((stay) => (
            <Card key={stay.id} className="overflow-hidden">
              <div className="h-48 bg-stone-100 flex items-center justify-center text-stone-400 font-light text-sm">
                [Property Image]
              </div>
              <CardHeader>
                <CardTitle>{stay.title}</CardTitle>
                <CardDescription>{stay.location}</CardDescription>
              </CardHeader>
              <CardContent className="flex justify-between items-center">
                <span className="font-semibold text-stone-900">{stay.price}</span>
                <Button variant="outline" size="sm">View Details</Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}