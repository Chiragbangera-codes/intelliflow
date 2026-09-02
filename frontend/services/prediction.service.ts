/**
 * Predictions API service — Phase 9.
 */

import apiClient from "./api";
import type { ApiResponse, PaginationMeta } from "@/types";
import type { Prediction, PredictionRequest } from "@/types/analytics";

const BASE = "/predictions";

export interface PredictionListResponse {
  data: Prediction[];
  meta: PaginationMeta;
}

export async function runPrediction(
  data: PredictionRequest,
): Promise<ApiResponse<Prediction>> {
  const res = await apiClient.post<ApiResponse<Prediction>>(BASE, data);
  return res.data;
}

export async function listPredictions(params?: {
  page?: number;
  page_size?: number;
}): Promise<{ success: boolean; message: string; data: Prediction[]; meta: PaginationMeta }> {
  const res = await apiClient.get(BASE, { params });
  return res.data;
}

export async function getPrediction(
  id: string,
): Promise<ApiResponse<Prediction>> {
  const res = await apiClient.get<ApiResponse<Prediction>>(`${BASE}/${id}`);
  return res.data;
}
