"use client";

import { useState } from "react";
import { ExtractedPage } from "@/lib/api";

interface ExtractedPageCardProps {
  page: ExtractedPage;
  totalPages: number;
}

export function ExtractedPageCard({ page, totalPages }: ExtractedPageCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(page.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback if clipboard API restricted
    }
  };

  const isBlank = page.text.trim().length === 0;

  return (
    <article
      aria-label={`Extracted content for Page ${page.page_number} of ${totalPages}`}
      className="rounded-lg border border-slate-200 bg-white shadow-xs transition-shadow hover:shadow-sm"
    >
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/50 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-md bg-slate-900 px-2.5 py-0.5 text-xs font-semibold text-white">
            Page {page.page_number} of {totalPages}
          </span>

          {page.has_images && (
            <span className="inline-flex items-center rounded-md border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800">
              Images Detected
            </span>
          )}

          {page.ocr_applied && (
            <span className="inline-flex items-center rounded-md border border-purple-200 bg-purple-50 px-2 py-0.5 text-[11px] font-semibold text-purple-800">
              OCR Extracted
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span>{page.word_count.toLocaleString()} words</span>
          <span>·</span>
          <span>{page.char_count.toLocaleString()} chars</span>

          {!isBlank && (
            <button
              type="button"
              onClick={handleCopy}
              className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-slate-900"
              aria-label={`Copy text from page ${page.page_number}`}
            >
              {copied ? (
                <>
                  <svg
                    className="h-3.5 w-3.5 text-emerald-600"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth="2"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="m4.5 12.75 6 6 9-13.5"
                    />
                  </svg>
                  <span className="text-emerald-700">Copied</span>
                </>
              ) : (
                <>
                  <svg
                    className="h-3.5 w-3.5 text-slate-500"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth="1.75"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 0 1-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 0 1 1.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9m9 15-3.375-3.375m0 0a8.966 8.966 0 0 1-5.625 2.625c-.621 0-1.125-.504-1.125-1.125v-9.75c0-.621.504-1.125 1.125-1.125h3.375"
                    />
                  </svg>
                  <span>Copy</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Page Content */}
      <div className="p-4">
        {isBlank ? (
          <p className="text-xs italic text-slate-400">
            (Blank page — no extractable text detected on this page)
          </p>
        ) : (
          <div className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-slate-800 break-words">
            {page.text}
          </div>
        )}
      </div>
    </article>
  );
}
