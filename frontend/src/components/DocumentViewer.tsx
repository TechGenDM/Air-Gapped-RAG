"use client";

import { useMemo, useState } from "react";
import { DocumentUploadResponse } from "@/lib/api";
import { ExtractedPageCard } from "./ExtractedPageCard";
import { QuestionAnsweringPanel } from "./QuestionAnsweringPanel";

interface DocumentViewerProps {
  document: DocumentUploadResponse;
  onReset: () => void;
}

export function DocumentViewer({ document, onReset }: DocumentViewerProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedId, setCopiedId] = useState(false);

  const totalWords = useMemo(() => {
    return document.pages.reduce((acc, p) => acc + p.word_count, 0);
  }, [document.pages]);

  const totalChars = useMemo(() => {
    return document.pages.reduce((acc, p) => acc + p.char_count, 0);
  }, [document.pages]);

  const filteredPages = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return document.pages;
    return document.pages.filter(
      (p) =>
        p.text.toLowerCase().includes(q) ||
        p.page_number.toString() === q
    );
  }, [document.pages, searchQuery]);

  const handleCopyId = async () => {
    try {
      await navigator.clipboard.writeText(document.document_id);
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 2000);
    } catch {
      // Fallback
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Document Overview Card */}
      <section
        aria-label="Document Metadata"
        className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs"
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-slate-900 break-all">
                {document.filename}
              </h2>
              <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800 border border-emerald-200">
                Extracted
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span>Document ID:</span>
              <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">
                {document.document_id}
              </code>
              <button
                type="button"
                onClick={handleCopyId}
                className="text-[11px] font-medium text-slate-700 hover:text-slate-900 underline underline-offset-2"
                aria-label="Copy Document ID"
              >
                {copiedId ? "Copied!" : "Copy ID"}
              </button>
            </div>
          </div>

          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-slate-900"
          >
            <svg
              className="h-4 w-4 text-slate-500"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth="2"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3"
              />
            </svg>
            Upload Another PDF
          </button>
        </div>

        {/* Aggregate Metrics Bar */}
        <div className="mt-5 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 sm:grid-cols-4">
          <div className="rounded-lg bg-slate-50 p-3 text-center">
            <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
              Total Pages
            </p>
            <p className="mt-0.5 text-xl font-bold text-slate-900">
              {document.total_pages}
            </p>
          </div>

          <div className="rounded-lg bg-slate-50 p-3 text-center">
            <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
              Total Words
            </p>
            <p className="mt-0.5 text-xl font-bold text-slate-900">
              {totalWords.toLocaleString()}
            </p>
          </div>

          <div className="rounded-lg bg-slate-50 p-3 text-center">
            <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
              Total Characters
            </p>
            <p className="mt-0.5 text-xl font-bold text-slate-900">
              {totalChars.toLocaleString()}
            </p>
          </div>

          <div className="rounded-lg bg-slate-50 p-3 text-center">
            <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
              Storage Engine
            </p>
            <p className="mt-0.5 text-xs font-semibold text-slate-700">
              Local (data/uploads)
            </p>
          </div>
        </div>
      </section>

      {/* Local Vector Indexing & Citation-Backed Q&A */}
      <QuestionAnsweringPanel
        documentId={document.document_id}
        filename={document.filename}
        totalPages={document.total_pages}
      />

      {/* Page Filtering & Results Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-bold text-slate-900">
            Extracted Pages
          </h3>
          <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-700">
            {filteredPages.length} {filteredPages.length === 1 ? "page" : "pages"}
          </span>
        </div>

        <div className="relative w-full sm:w-72">
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter extracted pages..."
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 placeholder:text-slate-400 focus-visible:border-slate-900 focus-visible:ring-1 focus-visible:ring-slate-900"
            aria-label="Filter pages by content"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-600"
              aria-label="Clear filter"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Pages List */}
      <div className="flex flex-col gap-4">
        {filteredPages.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
            <p className="text-sm font-medium text-slate-700">
              No pages match &ldquo;{searchQuery}&rdquo;
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Try searching with another term or page number.
            </p>
          </div>
        ) : (
          filteredPages.map((page) => (
            <ExtractedPageCard
              key={page.page_number}
              page={page}
              totalPages={document.total_pages}
            />
          ))
        )}
      </div>
    </div>
  );
}
