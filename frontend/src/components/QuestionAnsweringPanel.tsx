"use client";

import { useState } from "react";
import {
  AnswerResponse,
  ApiError,
  getAnswer,
  indexDocument,
} from "@/lib/api";

interface QuestionAnsweringPanelProps {
  documentId: string;
  filename: string;
  totalPages: number;
}

export function QuestionAnsweringPanel({
  documentId,
  filename,
  totalPages,
}: QuestionAnsweringPanelProps) {
  const [indexingState, setIndexingState] = useState<
    "idle" | "indexing" | "indexed" | "error"
  >("idle");
  const [indexedChunksCount, setIndexedChunksCount] = useState<number | null>(
    null
  );
  const [indexingError, setIndexingError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [answerResult, setAnswerResult] = useState<AnswerResponse | null>(null);

  const handleIndex = async (reindex = false) => {
    setIndexingState("indexing");
    setIndexingError(null);
    if (reindex) {
      setAnswerResult(null);
      setAskError(null);
    }

    try {
      const res = await indexDocument(documentId, reindex);
      setIndexedChunksCount(res.total_chunks);
      setIndexingState("indexed");
    } catch (err: unknown) {
      setIndexingState("error");
      if (err instanceof ApiError) {
        setIndexingError(err.detail);
      } else {
        setIndexingError("Failed to index document in local vector database.");
      }
    }
  };

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanQuery = query.trim();
    if (!cleanQuery || asking) return;

    // Immediately clear previous answer, citations, and errors before starting new request
    setAsking(true);
    setAskError(null);
    setAnswerResult(null);

    try {
      const res = await getAnswer(cleanQuery, documentId);
      setAnswerResult(res);
    } catch (err: unknown) {
      // Ensure stale answer and citations remain cleared on failure
      setAnswerResult(null);
      if (err instanceof ApiError) {
        setAskError(err.detail);
      } else {
        setAskError("An unexpected error occurred while communicating with the local LLM.");
      }
    } finally {
      setAsking(false);
    }
  };

  const setSuggestedQuery = (suggested: string) => {
    if (asking) return;
    setQuery(suggested);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Indexing Section */}
      <section
        aria-label="Vector Indexing Status"
        className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs"
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-slate-900">
                Local Vector Search &amp; Citations
              </h3>
              {indexingState === "indexed" && (
                <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800 border border-emerald-200">
                  Ready for Q&amp;A
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 leading-relaxed max-w-2xl">
              Index extracted pages into embedded LanceDB with local{" "}
              <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] text-slate-700">
                nomic-embed-text
              </code>{" "}
              embeddings to query answers backed by exact physical page citations.
            </p>
          </div>

          <div>
            {indexingState === "idle" && (
              <button
                type="button"
                onClick={() => handleIndex(false)}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-slate-800 focus-visible:ring-2 focus-visible:ring-slate-900 transition-colors"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="2"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"
                  />
                </svg>
                Index Document for Q&amp;A
              </button>
            )}

            {indexingState === "indexing" && (
              <div className="inline-flex items-center gap-2 rounded-lg bg-slate-100 px-4 py-2 text-xs font-semibold text-slate-700">
                <svg
                  className="h-4 w-4 animate-spin text-slate-600"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                  />
                </svg>
                Indexing in LanceDB...
              </div>
            )}

            {indexingState === "indexed" && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 font-mono">
                  {indexedChunksCount ?? totalPages} chunks indexed
                </span>
                <button
                  type="button"
                  onClick={() => handleIndex(true)}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 shadow-xs hover:bg-slate-50"
                  title="Re-run chunking and overwrite vector index"
                >
                  Re-index
                </button>
              </div>
            )}

            {indexingState === "error" && (
              <button
                type="button"
                onClick={() => handleIndex(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-red-300 bg-red-50 px-3.5 py-2 text-xs font-semibold text-red-700 hover:bg-red-100"
              >
                Retry Indexing
              </button>
            )}
          </div>
        </div>

        {indexingError && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50/70 p-3 text-xs text-red-700">
            <strong>Indexing Error:</strong> {indexingError}
          </div>
        )}
      </section>

      {/* Q&A Section */}
      <section
        aria-label="Citation-Backed Q&A"
        className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs"
      >
        <div className="space-y-1 pb-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-slate-900">
              Ask Document Questions
            </h3>
            <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-slate-700">
              Gemma 4 12B
            </span>
          </div>
          <p className="text-xs text-slate-500">
            Queries retrieve nearest semantic passages and prompt local Gemma to generate
            evidence-based answers with verified page numbers.
          </p>
        </div>

        {/* Question Form */}
        <form onSubmit={handleAsk} className="mt-5 space-y-3">
          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={indexingState !== "indexed" || asking}
              placeholder={
                indexingState === "indexed"
                  ? "e.g., What is the notice period for agreement termination?"
                  : "Index this document above to enable question answering..."
              }
              className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-xs text-slate-900 placeholder:text-slate-400 focus-visible:border-slate-900 focus-visible:ring-1 focus-visible:ring-slate-900 disabled:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed"
            />
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            {/* Suggested Starter Prompts */}
            <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
              <span className="text-[11px] text-slate-400">Suggestions:</span>
              <button
                type="button"
                disabled={indexingState !== "indexed" || asking}
                onClick={() => setSuggestedQuery("What is the governing law and jurisdiction?")}
                className="rounded bg-slate-100 hover:bg-slate-200 px-2 py-0.5 text-[11px] text-slate-700 disabled:opacity-50"
              >
                Governing Law
              </button>
              <button
                type="button"
                disabled={indexingState !== "indexed" || asking}
                onClick={() => setSuggestedQuery("What is the notice period for contract termination?")}
                className="rounded bg-slate-100 hover:bg-slate-200 px-2 py-0.5 text-[11px] text-slate-700 disabled:opacity-50"
              >
                Termination Notice
              </button>
              <button
                type="button"
                disabled={indexingState !== "indexed" || asking}
                onClick={() => setSuggestedQuery("What are the payment terms and schedule?")}
                className="rounded bg-slate-100 hover:bg-slate-200 px-2 py-0.5 text-[11px] text-slate-700 disabled:opacity-50"
              >
                Payment Terms
              </button>
            </div>

            <button
              type="submit"
              disabled={indexingState !== "indexed" || !query.trim() || asking}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-slate-800 focus-visible:ring-2 focus-visible:ring-slate-900 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed transition-colors"
            >
              {asking ? (
                <>
                  <svg
                    className="h-3.5 w-3.5 animate-spin text-white"
                    viewBox="0 0 24 24"
                    fill="none"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                    />
                  </svg>
                  Synthesizing Answer...
                </>
              ) : (
                "Ask Question"
              )}
            </button>
          </div>
        </form>

        {/* Error Banner */}
        {askError && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            <strong>Error:</strong> {askError}
          </div>
        )}

        {/* Answer Display */}
        {answerResult && (
          <div className="mt-6 space-y-4 border-t border-slate-100 pt-5">
            {/* Question Echo */}
            <div className="text-xs text-slate-500">
              <span>Question:</span>{" "}
              <strong className="text-slate-800">&ldquo;{answerResult.question}&rdquo;</strong>
            </div>

            {/* Insufficient Evidence Case */}
            {!answerResult.evidence_sufficient ||
            answerResult.answer.toLowerCase() === "not found in records" ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
                <div className="flex items-center gap-2 text-amber-900 font-semibold text-xs">
                  <svg
                    className="h-4 w-4 text-amber-700"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth="2"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z"
                    />
                  </svg>
                  Not found in records
                </div>
                <p className="mt-1 text-xs text-amber-800 leading-relaxed">
                  The retrieved document passages do not contain verifiable facts to answer
                  this inquiry. The local LLM strictly refrained from fabricating unverified claims.
                </p>
                <div className="mt-2 text-[11px] font-mono text-amber-700">
                  Model: {answerResult.model} · Latency: {answerResult.elapsed_seconds}s
                </div>
              </div>
            ) : (
              /* Verified Answer Case */
              <div className="space-y-4">
                <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-5">
                  <div className="flex items-center justify-between gap-2 border-b border-slate-200/60 pb-2.5">
                    <span className="text-xs font-semibold text-slate-700">
                      Synthesized Answer
                    </span>
                    <div className="flex items-center gap-2 text-[11px] text-slate-500 font-mono">
                      <span>{answerResult.model}</span>
                      <span>·</span>
                      <span>{answerResult.elapsed_seconds}s</span>
                    </div>
                  </div>

                  <p className="mt-3 text-sm text-slate-900 leading-relaxed whitespace-pre-wrap font-normal">
                    {answerResult.answer}
                  </p>

                  <p className="mt-3 text-[11px] text-slate-400 italic">
                    Informational synthesis only · Verify citations against original source pages below.
                  </p>
                </div>

                {/* Verified Citations */}
                {answerResult.sources && answerResult.sources.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                        Verified Source Citations
                      </h4>
                      <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[11px] font-semibold text-slate-700">
                        {answerResult.sources.length}
                      </span>
                    </div>

                    <div className="grid grid-cols-1 gap-3">
                      {answerResult.sources.map((src, idx) => (
                        <div
                          key={`${src.chunk_id}-${idx}`}
                          className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-2xs hover:border-slate-300 transition-colors"
                        >
                          <div className="flex items-center justify-between gap-2 mb-2">
                            <span className="inline-flex items-center gap-1 rounded-md bg-blue-50 px-2 py-0.5 text-xs font-bold text-blue-800 border border-blue-200">
                              <svg
                                className="h-3.5 w-3.5"
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
                              Page {src.page_number}
                            </span>
                            <span className="text-[11px] text-slate-400 font-mono truncate max-w-xs">
                              {src.filename || filename}
                            </span>
                          </div>

                          <div className="rounded bg-slate-50 border border-slate-100 p-2.5 text-xs font-mono text-slate-800 leading-relaxed whitespace-pre-wrap">
                            &ldquo;{src.excerpt}&rdquo;
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
