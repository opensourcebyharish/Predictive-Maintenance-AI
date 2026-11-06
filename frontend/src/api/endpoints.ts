/**
 * Typed endpoint functions - one per backend route used by the dashboard.
 * Keep every call free of business logic; pages consume these via hooks.
 */

import { api } from "@/api/client";
import type {
  AlertAcknowledgeResponse,
  AlertRecord,
  AlertStatus,
  AlertSummary,
  ApiHealth,
  ApiReadiness,
  DatasetId,
  EvaluationIndex,
  EvaluationReport,
  MachineDetail,
  MachineHealthSnapshot,
  MachineSummary,
  PaginatedPredictions,
  PaginatedReadings,
} from "@/api/types";

export function fetchHealth(): Promise<ApiHealth> {
  return api.request<ApiHealth>("/health");
}

export function fetchReadiness(): Promise<ApiReadiness> {
  return api.request<ApiReadiness>("/ready");
}

export function fetchMachines(): Promise<MachineSummary[]> {
  return api.request<MachineSummary[]>("/machines");
}

export function fetchMachine(machineId: string): Promise<MachineDetail> {
  return api.request<MachineDetail>(`/machines/${encodeURIComponent(machineId)}`);
}

export function fetchMachineHealth(machineId: string): Promise<MachineHealthSnapshot> {
  return api.request<MachineHealthSnapshot>(`/machines/${encodeURIComponent(machineId)}/health`);
}

export function fetchMachineReadings(
  machineId: string,
  limit = 100,
  offset = 0,
): Promise<PaginatedReadings> {
  return api.request<PaginatedReadings>(`/machines/${encodeURIComponent(machineId)}/readings`, {
    query: { limit, offset },
  });
}

export function fetchMachinePredictions(
  machineId: string,
  limit = 100,
  offset = 0,
): Promise<PaginatedPredictions> {
  return api.request<PaginatedPredictions>(`/machines/${encodeURIComponent(machineId)}/predictions`, {
    query: { limit, offset },
  });
}

export function fetchAlerts(options: {
  machineId?: string;
  status?: AlertStatus;
  limit?: number;
  offset?: number;
} = {}): Promise<AlertRecord[]> {
  return api.request<AlertRecord[]>("/alerts", {
    query: {
      machine_id: options.machineId,
      status: options.status,
      limit: options.limit ?? 200,
      offset: options.offset ?? 0,
    },
  });
}

export function fetchAlertSummary(): Promise<AlertSummary> {
  return api.request<AlertSummary>("/alerts/summary");
}

export function acknowledgeAlert(alertId: number): Promise<AlertAcknowledgeResponse> {
  return api.request<AlertAcknowledgeResponse>(`/alerts/${alertId}/acknowledge`, {
    method: "POST",
    body: { acknowledged_by: "dashboard" },
  });
}

/** Phase 4 evaluation reports served by the documented `GET /evaluation` route. */
export function fetchEvaluationIndex(): Promise<EvaluationIndex> {
  return api.request<EvaluationIndex>("/evaluation");
}

export function fetchEvaluationReport(datasetId: DatasetId): Promise<EvaluationReport> {
  return api.request<EvaluationReport>(`/evaluation/${datasetId}`);
}
