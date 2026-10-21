import type { Metadata } from "next";
import Link from "next/link";
import RegisterForm from "@/components/auth/RegisterForm";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card";

export const metadata: Metadata = {
  title: "Create an account | LikeHome",
};

const GRID_IMAGES = [
  "https://angiemcmonigal.com/wp-content/uploads/2022/07/Angie-McMonigal-Photography-3870.jpg",
  "https://freight.cargo.site/w/500/i/a520d8a8b0c318bea0a71cb91778cff15e801b79ed5504885e5587ab1f01bef4/RW-LICH-0068-web.jpg",
  "https://images.pexels.com/photos/32046648/pexels-photo-32046648/free-photo-of-modern-architectural-black-and-white-silhouette.jpeg",
  "https://freight.cargo.site/w/750/i/f37baf77db1aad93b7b5ac21547403ddb1901312217c87c38071fb6d024e3f28/MO-PARK3-0517-web.jpg",
  "https://www.macfilos.com/wp-content/uploads/2021/10/Jamesart00B.jpg",
  "https://mymodernmet.com/wp/wp-content/uploads/2020/04/agora-architecture-photo-contest-20.jpg"
];

export default function RegisterPage() {
  return (
    <div className="flex min-h-[calc(100vh-4rem)] w-full bg-canvas">
      
      {/* Left Side: 3x2 Architectural Image Grid */}
      <div className="relative hidden w-0 flex-1 lg:block bg-surface-muted border-r border-line overflow-hidden">
        <div className="absolute inset-0 grid grid-cols-3 grid-rows-2">
          {GRID_IMAGES.map((src, idx) => (
            <img
              key={idx}
              className="h-full w-full object-cover"
              src={src}
              alt={`Architectural mood board image ${idx + 1}`}
            />
          ))}
        </div>
        {/* Subtle overlay to blend the grid together and tint it slightly toward the brand ink color */}
        <div className="absolute inset-0 bg-ink/10 mix-blend-multiply pointer-events-none" />
      </div>

      {/* Right Side: Form */}
      <div className="flex flex-1 flex-col justify-center px-4 py-12 sm:px-6 lg:flex-none lg:w-1/2 xl:w-5/12">
        <div className="mx-auto w-full max-w-sm">
          <Card className="border-transparent shadow-none bg-transparent sm:border-line sm:bg-surface sm:shadow-sm">
            <CardHeader className="space-y-1 text-center pb-4">
              <CardTitle className="text-2xl font-semibold tracking-tight text-ink">
                Create an account
              </CardTitle>
              <CardDescription className="text-muted">
                Book stays, manage reservations, and earn reward points.
              </CardDescription>
            </CardHeader>

            <CardContent>
              <RegisterForm />
            </CardContent>

            <CardFooter className="justify-center border-t border-line py-5 mt-4">
              <p className="text-sm text-muted">
                Already have an account?{" "}
                <Link href="/login" className="font-bold text-ink hover:text-accent transition-colors">
                  Sign in
                </Link>
              </p>
            </CardFooter>
          </Card>
        </div>
      </div>

    </div>
  );
}