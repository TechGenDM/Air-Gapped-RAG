"use client";

import { useRef, useState } from "react";
import { uploadDocument, ApiError, DocumentUploadResponse } from "@/lib/api";

interface FileUploadZoneProps {
  onUploadSuccess: (data: DocumentUploadResponse) => void;
}

export function FileUploadZone({ onUploadSuccess }: FileUploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      processFile(files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      processFile(files[0]);
    }
  };

  const processFile = async (file: File) => {
    setErrorMessage(null);
    setSelectedFile(file);
    setIsUploading(true);

    try {
      const result = await uploadDocument(file);
      onUploadSuccess(result);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("An unexpected error occurred while processing the document.");
      }
    } finally {
      setIsUploading(false);
      // Reset input value so re-uploading the same file triggers change event
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const triggerPicker = () => {
    if (!isUploading) {
      fileInputRef.current?.click();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      triggerPicker();
    }
  };

  return (
    <div className="w-full">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="sr-only"
        onChange={handleFileInputChange}
        tabIndex={-1}
        aria-hidden="true"
      />

      <div
        role="button"
        tabIndex={0}
        aria-label="Upload PDF Document"
        onClick={triggerPicker}
        onKeyDown={handleKeyDown}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 sm:p-12 text-center transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 ${
          isDragging
            ? "border-slate-800 bg-slate-100"
            : "border-slate-300 bg-white hover:border-slate-400 hover:bg-slate-50/50"
        } ${isUploading ? "pointer-events-none opacity-80" : ""}`}
      >
        {isUploading ? (
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-900 border-t-transparent" />
            <div className="text-sm font-semibold text-slate-900">
              Processing & Extracting Pages...
            </div>
            <p className="text-xs text-slate-500">
              Parsing {selectedFile?.name || "document"} with PyMuPDF locally
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center">
            {/* Minimal Document Icon */}
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
              <svg
                className="h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth="1.75"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
                />
              </svg>
            </div>

            <div className="text-sm font-semibold text-slate-900">
              <span className="text-slate-900 underline underline-offset-2">Click to select a file</span> or drag and drop
            </div>
            <p className="mt-1.5 text-xs text-slate-500">
              PDF documents only · Maximum file size 50 MB
            </p>
          </div>
        )}
      </div>

      {errorMessage && (
        <div
          role="alert"
          className="mt-4 flex items-start justify-between rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900"
        >
          <div className="flex gap-2.5">
            <svg
              className="h-5 w-5 flex-shrink-0 text-red-600"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
                clipRule="evenodd"
              />
            </svg>
            <div>
              <p className="font-semibold text-red-950">Extraction Failed</p>
              <p className="mt-0.5 text-xs text-red-800">{errorMessage}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="rounded p-1 text-red-700 hover:bg-red-100 focus-visible:ring-2 focus-visible:ring-red-900"
            aria-label="Dismiss error"
          >
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}
