/**
 * Typed API client for Air-Gapped RAG local backend.
 */

export interface ExtractedPage {
  page_number: number;
  text: string;
  char_count: number;
  word_count: number;
  has_images: boolean;
  ocr_applied?: boolean;
}

export interface DocumentUploadResponse {
  document_id: string;
  filename: string;
  total_pages: number;
  pages: ExtractedPage[];
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
}

export interface IndexDocumentResponse {
  document_id: string;
  filename: string;
  total_pages: number;
  total_chunks: number;
  reindexed: boolean;
  message: string;
}

export interface SourceReference {
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number: number;
  excerpt: string;
}

export interface AnswerResponse {
  question: string;
  answer: string;
  sources: SourceReference[];
  evidence_sufficient: boolean;
  model: string;
  elapsed_seconds: number;
}

export class ApiError extends Error {
  public status: number;
  public detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024; // 50 MB

export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
}

/**
 * Check backend health and readiness.
 */
export async function checkBackendHealth(): Promise<HealthResponse> {
  const baseUrl = getApiBaseUrl();
  try {
    const res = await fetch(`${baseUrl}/health`, {
      method: "GET",
      cache: "no-store",
    });

    if (!res.ok) {
      throw new ApiError(res.status, `Backend returned status ${res.status}`);
    }

    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(
      0,
      `Cannot connect to local backend at ${baseUrl}. Ensure the FastAPI server is running.`
    );
  }
}

/**
 * Upload a PDF document to the local FastAPI backend and extract its pages.
 */
export async function uploadDocument(file: File): Promise<DocumentUploadResponse> {
  // Pre-flight client checks
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    throw new ApiError(
      415,
      "Unsupported file format. Please select a valid PDF file (.pdf)."
    );
  }

  if (file.size === 0) {
    throw new ApiError(400, "The selected PDF file is empty (0 bytes).");
  }

  if (file.size > MAX_FILE_SIZE_BYTES) {
    throw new ApiError(
      413,
      `File size (${(file.size / (1024 * 1024)).toFixed(1)} MB) exceeds the 50 MB maximum limit.`
    );
  }

  const formData = new FormData();
  formData.append("file", file, file.name);

  const baseUrl = getApiBaseUrl();
  let res: Response;

  try {
    res = await fetch(`${baseUrl}/api/v1/documents/upload`, {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new ApiError(
      0,
      `Network error: Failed to reach backend at ${baseUrl}. Ensure the FastAPI server is running.`
    );
  }

  if (!res.ok) {
    let errorDetail = `Upload failed with HTTP status ${res.status}`;
    try {
      const errorJson = await res.json();
      if (errorJson && typeof errorJson.detail === "string") {
        errorDetail = errorJson.detail;
      }
    } catch {
      // Body not JSON
    }
    throw new ApiError(res.status, errorDetail);
  }

  return await res.json();
}

/**
 * Trigger local vector indexing of an uploaded document in LanceDB.
 */
export async function indexDocument(
  documentId: string,
  reindex = false
): Promise<IndexDocumentResponse> {
  const baseUrl = getApiBaseUrl();
  let res: Response;

  try {
    res = await fetch(
      `${baseUrl}/api/v1/documents/${documentId}/index?reindex=${reindex}`,
      {
        method: "POST",
      }
    );
  } catch {
    throw new ApiError(
      0,
      `Network error: Failed to reach backend at ${baseUrl}. Ensure the FastAPI server is running.`
    );
  }

  if (!res.ok) {
    let errorDetail = `Indexing failed with HTTP status ${res.status}`;
    try {
      const errorJson = await res.json();
      if (errorJson && typeof errorJson.detail === "string") {
        errorDetail = errorJson.detail;
      }
    } catch {
      // Body not JSON
    }
    throw new ApiError(res.status, errorDetail);
  }

  return await res.json();
}

/**
 * Ask a question about the document and receive an evidence-backed answer with citations.
 */
export async function getAnswer(
  query: string,
  documentId?: string,
  limit = 4
): Promise<AnswerResponse> {
  const cleanQuery = query.trim();
  if (!cleanQuery) {
    throw new ApiError(400, "Please enter a question to ask.");
  }

  const baseUrl = getApiBaseUrl();
  let res: Response;

  try {
    res = await fetch(`${baseUrl}/api/v1/answer`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query: cleanQuery,
        document_id: documentId || null,
        limit,
      }),
    });
  } catch {
    throw new ApiError(
      0,
      `Network error: Failed to reach backend at ${baseUrl}. Ensure the FastAPI server is running.`
    );
  }

  if (!res.ok) {
    let errorDetail = `Answer request failed with HTTP status ${res.status}`;
    try {
      const errorJson = await res.json();
      if (errorJson && typeof errorJson.detail === "string") {
        errorDetail = errorJson.detail;
      }
    } catch {
      // Body not JSON
    }
    throw new ApiError(res.status, errorDetail);
  }

  return await res.json();
}
