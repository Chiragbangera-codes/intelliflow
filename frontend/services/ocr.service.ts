/**
 * OCR & Text Extraction service.
 *
 * Provides API client calls for:
 *   - Triggering asynchronous OCR on documents
 *   - Polling OCR Celery job execution status
 *   - Fetching extracted text and ordered document chunks
 */

import apiClient from "./api";
import type {
  ApiResponse,
  DocumentTextResponse,
  OCRJobData,
  OCRStatusData,
} from "@/types";

/**
 * Enqueue an asynchronous OCR & text extraction job for a document.
 *
 * @param documentId - UUID of the target document.
 */
export async function startOCR(
  documentId: string,
): Promise<ApiResponse<OCRJobData>> {
  const response = await apiClient.post<ApiResponse<OCRJobData>>(
    `/documents/${documentId}/ocr`,
  );
  return response.data;
}

/**
 * Check the status of an ongoing Celery OCR task.
 *
 * @param jobId - The Celery task ID returned by startOCR.
 */
export async function getOCRJobStatus(
  jobId: string,
): Promise<ApiResponse<OCRStatusData>> {
  const response = await apiClient.get<ApiResponse<OCRStatusData>>(
    `/ocr/jobs/${jobId}`,
  );
  return response.data;
}

/**
 * Retrieve the full extracted text and chunk breakdown for a document.
 *
 * @param documentId - UUID of the target document.
 */
export async function getDocumentText(
  documentId: string,
): Promise<ApiResponse<DocumentTextResponse>> {
  const response = await apiClient.get<ApiResponse<DocumentTextResponse>>(
    `/documents/${documentId}/text`,
  );
  return response.data;
}
