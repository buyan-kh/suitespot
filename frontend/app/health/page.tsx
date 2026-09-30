"use client";

import { useEffect, useState } from "react";

interface HealthData {
  status: string;
  database: string;
  version: string;
}

export default function HealthPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://localhost:8000/health")
      .then((res) => res.json())
      .then((data) => {
        setHealth(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-stone-50">
      <div className="bg-white rounded-lg shadow-md p-8 max-w-md w-full">
        <h1 className="text-2xl font-bold mb-6 text-stone-900">
          API Health Check
        </h1>
        {loading && <p className="text-stone-500">Checking API status...</p>}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded p-4">
            <p className="text-red-700 font-medium">API Unreachable</p>
            <p className="text-red-500 text-sm mt-1">{error}</p>
          </div>
        )}
        {health && (
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-stone-600">Status</span>
              <span className="font-medium text-green-600">
                {health.status}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-stone-600">Database</span>
              <span
                className={`font-medium ${health.database === "healthy" ? "text-green-600" : "text-red-600"}`}
              >
                {health.database}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-stone-600">Version</span>
              <span className="font-medium text-stone-900">
                {health.version}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
