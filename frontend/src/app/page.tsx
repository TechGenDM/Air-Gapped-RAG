"use client";

import { useState } from "react";
import { DocumentUploadResponse } from "@/lib/api";
import { Header } from "@/components/Header";
import { FileUploadZone } from "@/components/FileUploadZone";
import { DocumentViewer } from "@/components/DocumentViewer";

export default function Home() {
  const [extractedDocument, setExtractedDocument] =
    useState<DocumentUploadResponse | null>(null);

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Header />

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
        {!extractedDocument ? (
          <div className="flex flex-col gap-8">
            {/* Hero / Introduction */}
            <div className="text-center max-w-2xl mx-auto space-y-2">
              <span className="inline-flex items-center rounded-full bg-slate-200/70 px-3 py-1 text-xs font-semibold text-slate-800">
                Milestone 1 · Local PDF Ingestion
              </span>
              <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
                Upload Document for Local Intelligence
              </h2>
              <p className="text-sm text-slate-600 leading-relaxed">
                Upload contracts or legal documents to extract text and physical page boundaries.
                All parsing and vector indexing execute locally on your machine with no external network calls.
              </p>
            </div>

            {/* Upload Zone */}
            <div className="max-w-2xl mx-auto w-full">
              <FileUploadZone onUploadSuccess={setExtractedDocument} />
            </div>

            {/* Architecture Guarantees */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-6 border-t border-slate-200">
              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
                <div className="flex items-center gap-2 text-slate-900 font-semibold text-sm">
                  <svg
                    className="h-4 w-4 text-slate-600"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth="2"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25"
                    />
                  </svg>
                  Exact Page Citations
                </div>
                <p className="mt-1 text-xs text-slate-500 leading-relaxed">
                  Extracts text with 1-indexed physical page numbering to ensure evidence-backed answers.
                </p>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
                <div className="flex items-center gap-2 text-slate-900 font-semibold text-sm">
                  <svg
                    className="h-4 w-4 text-slate-600"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth="2"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"
                    />
                  </svg>
                  Local-First Architecture
                </div>
                <p className="mt-1 text-xs text-slate-500 leading-relaxed">
                  Designed for offline execution. Documents and vector embeddings remain on your local machine.
                </p>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
                <div className="flex items-center gap-2 text-slate-900 font-semibold text-sm">
                  <svg
                    className="h-4 w-4 text-slate-600"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth="2"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 5.625c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125m16.5 5.625c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125"
                    />
                  </svg>
                  Sanitized UUID Storage
                </div>
                <p className="mt-1 text-xs text-slate-500 leading-relaxed">
                  Files are saved under local UUIDs to isolate against path traversal and metadata tampering.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <DocumentViewer
            document={extractedDocument}
            onReset={() => setExtractedDocument(null)}
          />
        )}
      </main>

      <footer className="border-t border-slate-200 bg-white py-4">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-slate-500">
          <span>Air-Gapped RAG · Hacktoberfest 2026 Week 2 Open-Source AI Challenge</span>
          <span className="font-mono text-[11px] text-slate-400">Local-First & Offline</span>
        </div>
      </footer>
    </div>
  );
}
