/**
 * Document service (Milestone 11).
 *
 * Full enterprise document intelligence client API:
 *   - Uploads with progress & metadata
 *   - Document Versioning (upload, list, restore, download version)
 *   - Access Grants & Sharing (share, list, update, revoke)
 *   - Lifecycle Transitions (activate, archive, restore, expire)
 *   - Multi-dimensional filtering & pagination
 *   - Bulk Operations (archive, restore, delete, tag, share)
 *   - Document AI Summary & Grounded Conversational Chat
 *   - Document Activity Timeline
 *   - Secure Downloads and Inline Preview URLs
 */

import apiClient from "./api";
import type {
  ApiResponse,
  BulkOperationResponse,
  CreateDocumentRequest,
  DocumentAISummaryResponse,
  DocumentAIChatRequest,
  DocumentAIChatResponse,
  DocumentActivityResponse,
  DocumentQueryParams,
  DocumentShare,
  DocumentSharePermission,
  DocumentVersion,
  EnterpriseDocument,
  UpdateDocumentRequest,
} from "@/types";

export interface UploadDocumentOptions {
  title?: string;
  description?: string;
  category?: string;
  document_type?: string;
  tags?: string[];
  department_id?: string;
  confidentiality?: string;
  retention_period_days?: number;
  expires_at?: string;
  onUploadProgress?: (progressPercent: number) => void;
}

// ---------------------------------------------------------------------------
// 1. Upload & CRUD
// ---------------------------------------------------------------------------

export async function uploadDocument(
  file: File,
  options?: UploadDocumentOptions,
): Promise<ApiResponse<EnterpriseDocument>> {
  const formData = new FormData();
  formData.append("file", file);

  if (options?.title) formData.append("title", options.title);
  if (options?.description) formData.append("description", options.description);
  if (options?.category) formData.append("category", options.category);
  if (options?.document_type) formData.append("document_type", options.document_type);
  if (options?.tags && options.tags.length > 0) {
    formData.append("tags", JSON.stringify(options.tags));
  }
  if (options?.department_id) formData.append("department_id", options.department_id);
  if (options?.confidentiality) formData.append("confidentiality", options.confidentiality);
  if (options?.retention_period_days) {
    formData.append("retention_period_days", String(options.retention_period_days));
  }
  if (options?.expires_at) formData.append("expires_at", options.expires_at);

  const response = await apiClient.post<ApiResponse<EnterpriseDocument>>(
    "/documents/upload",
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && options?.onUploadProgress) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          options.onUploadProgress(percent);
        }
      },
    },
  );

  return response.data;
}

export async function getDocuments(
  params: DocumentQueryParams = {},
): Promise<ApiResponse<EnterpriseDocument[]>> {
  const queryParams: Record<string, string | number | boolean> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  };

  if (params.search && params.search.trim()) queryParams.search = params.search.trim();
  if (params.status && params.status !== "all") queryParams.status = params.status;
  if (params.lifecycle_status && params.lifecycle_status !== "all") {
    queryParams.lifecycle_status = params.lifecycle_status;
  }
  if (params.department_id) queryParams.department_id = params.department_id;
  if (params.owner_id) queryParams.owner_id = params.owner_id;
  if (params.category) queryParams.category = params.category;
  if (params.document_type) queryParams.document_type = params.document_type;
  if (params.confidentiality && params.confidentiality !== "all") {
    queryParams.confidentiality = params.confidentiality;
  }
  if (params.tag) queryParams.tag = params.tag;
  if (params.shared_with_me !== undefined) queryParams.shared_with_me = params.shared_with_me;
  if (params.date_from) queryParams.date_from = params.date_from;
  if (params.date_to) queryParams.date_to = params.date_to;
  if (params.sort) queryParams.sort = params.sort;

  const response = await apiClient.get<ApiResponse<EnterpriseDocument[]>>("/documents", {
    params: queryParams,
  });

  return response.data;
}

export async function getDocument(id: string): Promise<ApiResponse<EnterpriseDocument>> {
  const response = await apiClient.get<ApiResponse<EnterpriseDocument>>(`/documents/${id}`);
  return response.data;
}

export async function createDocument(
  data: CreateDocumentRequest,
): Promise<ApiResponse<EnterpriseDocument>> {
  const response = await apiClient.post<ApiResponse<EnterpriseDocument>>("/documents", data);
  return response.data;
}

export async function updateDocument(
  id: string,
  data: UpdateDocumentRequest,
): Promise<ApiResponse<EnterpriseDocument>> {
  const response = await apiClient.patch<ApiResponse<EnterpriseDocument>>(`/documents/${id}`, data);
  return response.data;
}

export async function deleteDocument(id: string): Promise<ApiResponse<void>> {
  const response = await apiClient.delete<ApiResponse<void>>(`/documents/${id}`);
  return response.data;
}

// ---------------------------------------------------------------------------
// 2. Download & Preview
// ---------------------------------------------------------------------------

export async function downloadDocument(id: string, fileName: string): Promise<void> {
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

export async function previewDocumentBlob(id: string): Promise<{ blobUrl: string; contentType: string }> {
  const response = await apiClient.get(`/documents/${id}/preview`, {
    responseType: "blob",
  });
  const contentType = String(response.headers["content-type"] || "application/octet-stream");
  const blob = new Blob([response.data as BlobPart], { type: contentType });
  const blobUrl = window.URL.createObjectURL(blob);
  return { blobUrl, contentType };
}

// ---------------------------------------------------------------------------
// 3. Versioning
// ---------------------------------------------------------------------------

export async function uploadDocumentVersion(
  documentId: string,
  file: File,
  changeSummary?: string,
  onUploadProgress?: (percent: number) => void,
): Promise<ApiResponse<DocumentVersion>> {
  const formData = new FormData();
  formData.append("file", file);
  if (changeSummary) formData.append("change_summary", changeSummary);

  const response = await apiClient.post<ApiResponse<DocumentVersion>>(
    `/documents/${documentId}/versions`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e) => {
        if (e.total && onUploadProgress) {
          onUploadProgress(Math.round((e.loaded * 100) / e.total));
        }
      },
    },
  );
  return response.data;
}

export async function listDocumentVersions(
  documentId: string,
): Promise<ApiResponse<DocumentVersion[]>> {
  const response = await apiClient.get<ApiResponse<DocumentVersion[]>>(
    `/documents/${documentId}/versions`,
  );
  return response.data;
}

export async function restoreDocumentVersion(
  documentId: string,
  versionId: string,
): Promise<ApiResponse<DocumentVersion>> {
  const response = await apiClient.post<ApiResponse<DocumentVersion>>(
    `/documents/${documentId}/versions/${versionId}/restore`,
  );
  return response.data;
}

export async function downloadDocumentVersion(
  documentId: string,
  versionId: string,
  fileName: string,
): Promise<void> {
  const response = await apiClient.get(
    `/documents/${documentId}/versions/${versionId}/download`,
    { responseType: "blob" },
  );
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

// ---------------------------------------------------------------------------
// 4. Sharing & Access Grants
// ---------------------------------------------------------------------------

export async function shareDocument(
  documentId: string,
  userId: string,
  permission: DocumentSharePermission,
  expiresAt?: string | null,
): Promise<ApiResponse<DocumentShare>> {
  const response = await apiClient.post<ApiResponse<DocumentShare>>(
    `/documents/${documentId}/shares`,
    {
      user_id: userId,
      permission,
      expires_at: expiresAt || null,
    },
  );
  return response.data;
}

export async function listDocumentShares(
  documentId: string,
): Promise<ApiResponse<DocumentShare[]>> {
  const response = await apiClient.get<ApiResponse<DocumentShare[]>>(
    `/documents/${documentId}/shares`,
  );
  return response.data;
}

export async function updateDocumentShare(
  documentId: string,
  shareId: string,
  permission: DocumentSharePermission,
  expiresAt?: string | null,
): Promise<ApiResponse<DocumentShare>> {
  const response = await apiClient.patch<ApiResponse<DocumentShare>>(
    `/documents/${documentId}/shares/${shareId}`,
    {
      permission,
      expires_at: expiresAt || null,
    },
  );
  return response.data;
}

export async function revokeDocumentShare(
  documentId: string,
  shareId: string,
): Promise<ApiResponse<void>> {
  const response = await apiClient.delete<ApiResponse<void>>(
    `/documents/${documentId}/shares/${shareId}`,
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// 5. Lifecycle Management
// ---------------------------------------------------------------------------

export async function activateDocument(id: string): Promise<ApiResponse<EnterpriseDocument>> {
  const response = await apiClient.post<ApiResponse<EnterpriseDocument>>(`/documents/${id}/activate`);
  return response.data;
}

export async function archiveDocument(id: string): Promise<ApiResponse<EnterpriseDocument>> {
  const response = await apiClient.post<ApiResponse<EnterpriseDocument>>(`/documents/${id}/archive`);
  return response.data;
}

export async function restoreDocument(id: string): Promise<ApiResponse<EnterpriseDocument>> {
  const response = await apiClient.post<ApiResponse<EnterpriseDocument>>(`/documents/${id}/restore`);
  return response.data;
}

export async function expireDocument(id: string): Promise<ApiResponse<EnterpriseDocument>> {
  const response = await apiClient.post<ApiResponse<EnterpriseDocument>>(`/documents/${id}/expire`);
  return response.data;
}

// ---------------------------------------------------------------------------
// 6. Bulk Operations
// ---------------------------------------------------------------------------

export async function bulkArchiveDocuments(
  documentIds: string[],
): Promise<ApiResponse<BulkOperationResponse>> {
  const response = await apiClient.post<ApiResponse<BulkOperationResponse>>(
    "/documents/bulk/archive",
    { document_ids: documentIds },
  );
  return response.data;
}

export async function bulkRestoreDocuments(
  documentIds: string[],
): Promise<ApiResponse<BulkOperationResponse>> {
  const response = await apiClient.post<ApiResponse<BulkOperationResponse>>(
    "/documents/bulk/restore",
    { document_ids: documentIds },
  );
  return response.data;
}

export async function bulkDeleteDocuments(
  documentIds: string[],
): Promise<ApiResponse<BulkOperationResponse>> {
  const response = await apiClient.post<ApiResponse<BulkOperationResponse>>(
    "/documents/bulk/delete",
    { document_ids: documentIds },
  );
  return response.data;
}

export async function bulkTagDocuments(
  documentIds: string[],
  tags: string[],
  replace = false,
): Promise<ApiResponse<BulkOperationResponse>> {
  const response = await apiClient.post<ApiResponse<BulkOperationResponse>>(
    "/documents/bulk/tag",
    { document_ids: documentIds, tags, replace },
  );
  return response.data;
}

export async function bulkShareDocuments(
  documentIds: string[],
  userId: string,
  permission: DocumentSharePermission,
  expiresAt?: string | null,
): Promise<ApiResponse<BulkOperationResponse>> {
  const response = await apiClient.post<ApiResponse<BulkOperationResponse>>(
    "/documents/bulk/share",
    {
      document_ids: documentIds,
      user_id: userId,
      permission,
      expires_at: expiresAt || null,
    },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// 7. Document AI Intelligence & Activity
// ---------------------------------------------------------------------------

export async function getDocumentAISummary(
  documentId: string,
): Promise<ApiResponse<DocumentAISummaryResponse>> {
  const response = await apiClient.post<ApiResponse<DocumentAISummaryResponse>>(
    `/documents/${documentId}/ai/summary`,
  );
  return response.data;
}

export async function askDocumentAIChat(
  documentId: string,
  request: DocumentAIChatRequest,
): Promise<ApiResponse<DocumentAIChatResponse>> {
  const response = await apiClient.post<ApiResponse<DocumentAIChatResponse>>(
    `/documents/${documentId}/ai/chat`,
    request,
  );
  return response.data;
}

export async function getDocumentActivity(
  documentId: string,
  limit = 50,
  offset = 0,
): Promise<ApiResponse<DocumentActivityResponse>> {
  const response = await apiClient.get<ApiResponse<DocumentActivityResponse>>(
    `/documents/${documentId}/activity`,
    { params: { limit, offset } },
  );
  return response.data;
}
