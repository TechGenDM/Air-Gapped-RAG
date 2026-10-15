"use client";

import { useEffect, useState } from "react";
import { checkBackendHealth, HealthResponse } from "@/lib/api";

export function Header() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [checking, setChecking] = useState(true);
  const [isError, setIsError] = useState(false);

  useEffect(() => {
    let isMounted = true;

    async function check() {
      try {
        const data = await checkBackendHealth();
        if (isMounted) {
          setHealth(data);
          setIsError(false);
          setChecking(false);
        }
      } catch {
        if (isMounted) {
          setIsError(true);
          setHealth(null);
          setChecking(false);
        }
      }
    }

    check();

    return () => {
      isMounted = false;
    };
  }, []);

  const handleRetry = async () => {
    setChecking(true);
    setIsError(false);
    try {
      const data = await checkBackendHealth();
      setHealth(data);
    } catch {
      setIsError(true);
      setHealth(null);
    } finally {
      setChecking(false);
    }
  };

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold tracking-tight text-slate-900">
              Air-Gapped RAG
            </h1>
            <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700 border border-slate-200">
              Local-First
            </span>
          </div>
          <p className="mt-0.5 text-xs text-slate-500">
            PDF question-answering with exact page citations & evidence
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div
            className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium border ${
              checking
                ? "bg-slate-50 text-slate-600 border-slate-200"
                : isError
                ? "bg-amber-50 text-amber-800 border-amber-200"
                : "bg-emerald-50 text-emerald-800 border-emerald-200"
            }`}
            role="status"
            aria-live="polite"
          >
            <span
              className={`h-2 w-2 rounded-full ${
                checking
                  ? "bg-slate-400 animate-pulse"
                  : isError
                  ? "bg-amber-500"
                  : "bg-emerald-500"
              }`}
            />
            {checking
              ? "Checking Backend..."
              : isError
              ? "Backend Offline (Port 8000)"
              : `FastAPI Online (v${health?.version || "0.1.0"})`}
          </div>

          {isError && (
            <button
              onClick={handleRetry}
              type="button"
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-slate-900"
              title="Retry connection to local FastAPI backend"
            >
              Retry
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
