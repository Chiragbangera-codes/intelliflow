/**
 * Document service.
 *
 * Provides API client calls for document management:
 *   - Streaming multipart file upload with progress tracking
 *   - Secure authenticated binary file download
 *   - Search, status filtering, and sorting
 *   - Document metadata CRUD operations
 */

import apiClient from "./api";
import type {
  ApiResponse,
  CreateDocumentRequest,
  Document,
  DocumentQueryParams,
  UpdateDocumentRequest,
} from "@/types";

/**
 * Upload a document file with upload progress monitoring.
 *
 * @param file - The raw File object selected by user.
 * @param onUploadProgress - Callback receiving integer percentage (0-100).
 */
export async function uploadDocument(
  file: File,
  onUploadProgress?: (progressPercent: number) => void,
): Promise<ApiResponse<Document>> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiClient.post<ApiResponse<Document>>(
    "/documents/upload",
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onUploadProgress) {
          const percent = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total,
          );
          onUploadProgress(percent);
        }
      },
    },
  );

  return response.data;
}

/**
 * Download a document file as a binary blob and trigger browser save dialog.
 *
 * @param id - The document UUID.
 * @param fileName - Target filename for the saved file.
 */
export async function downloadDocument(
  id: string,
  fileName: string,
): Promise<void> {
  const response = await apiClient.get(`/documents/${id}/download`, {
    responseType: "blob",
  });

  const blob = new Blob([response.data]);
  const downloadUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = downloadUrl;
  link.setAttribute("download", fileName || "download");
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(downloadUrl);
}

/**
 * Retrieve a paginated, filtered, and sorted list of documents.
 */
export async function getDocuments(
  params: DocumentQueryParams = {},
): Promise<ApiResponse<Document[]>> {
  const queryParams: Record<string, string | number> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  };

  if (params.search && params.search.trim()) {
    queryParams.search = params.search.trim();
  }

  if (params.status && params.status !== "all") {
    queryParams.status = params.status;
  }

  if (params.sort) {
    queryParams.sort = params.sort;
  }

  const response = await apiClient.get<ApiResponse<Document[]>>("/documents", {
    params: queryParams,
  });

  return response.data;
}

/**
 * Retrieve metadata for a single document by UUID.
 */
export async function getDocument(id: string): Promise<ApiResponse<Document>> {
  const response = await apiClient.get<ApiResponse<Document>>(`/documents/${id}`);
  return response.data;
}

/**
 * Create a document metadata record (backwards compatibility).
 */
export async function createDocument(
  data: CreateDocumentRequest,
): Promise<ApiResponse<Document>> {
  const response = await apiClient.post<ApiResponse<Document>>("/documents", data);
  return response.data;
}

/**
 * Update document metadata fields (file_name, file_type, checksum).
 */
export async function updateDocument(
  id: string,
  data: UpdateDocumentRequest,
): Promise<ApiResponse<Document>> {
  const response = await apiClient.patch<ApiResponse<Document>>(`/documents/${id}`, data);
  return response.data;
}

/**
 * Soft-delete a document by UUID.
 */
export async function deleteDocument(id: string): Promise<ApiResponse<void>> {
  const response = await apiClient.delete<ApiResponse<void>>(`/documents/${id}`);
  return response.data;
}
