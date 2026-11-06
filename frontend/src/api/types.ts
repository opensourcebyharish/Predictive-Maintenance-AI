/**
 * TypeScript contracts mirroring the FastAPI Pydantic schemas
 * (src/predictive_maintenance/api/schemas.py). Field names and nullability are
 * kept 1:1 with the backend so a schema change fails typechecking here.
 */

// ---------------------------------------------------------------------------
// Enums (const objects instead of TS enums - erasableSyntaxOnly)
// ---------------------------------------------------------------------------

export const MACHINE_HEALTH = [
  "healthy",
  "anomalous",
  "elevated_risk",
  "critical_risk",
  "unknown",
] as const;
export type MachineHealth = (typeof MACHINE_HEALTH)[number];

export const ALERT_TYPES = [
  "anomaly_detected",
  "elevated_failure_risk",
  "critical_failure_risk",
  "machine_recovered",
] as const;
export type AlertType = (typeof ALERT_TYPES)[number];

export const ALERT_SEVERITIES = ["low", "medium", "high", "critical"] as const;
export type AlertSeverity = (typeof ALERT_SEVERITIES)[number];

export const ALERT_STATUSES = ["active", "acknowledged", "resolved"] as const;
export type AlertStatus = (typeof ALERT_STATUSES)[number];

export const DATASET_IDS = ["FD001", "FD002", "FD003", "FD004"] as const;
export type DatasetId = (typeof DATASET_IDS)[number];

// ---------------------------------------------------------------------------
// Health / readiness
// ---------------------------------------------------------------------------

export interface ApiHealth {
  status: string;
  app: string;
  version: string;
  service_loaded: boolean;
}

export interface ReadinessDataset {
  ready: boolean;
  default_model: string | null;
  models: Record<string, string>;
  error: string | null;
}

export interface ApiReadiness {
  ready: boolean;
  datasets: Record<string, ReadinessDataset>;
}

// ---------------------------------------------------------------------------
// Machines
// ---------------------------------------------------------------------------

export interface MachineSummary {
  machine_id: string;
  dataset_id: string;
  reading_count: number;
  first_cycle: number | null;
  last_cycle: number | null;
  latest_reading_at: string | null;
  health: MachineHealth;
}

export interface PredictionRecord {
  id: number;
  reading_id: number;
  machine_id: string;
  model: string;
  model_version: string;
  predicted_at: string;
  anomaly_score: number | null;
  anomaly_status: boolean | null;
  failure_probability: number | null;
  failure_status: boolean | null;
}

export interface MachineDetail extends MachineSummary {
  latest_sensor_values: Record<string, number> | null;
  latest_prediction: PredictionRecord | null;
  active_alerts: number;
}

export interface ReadingRecord {
  id: number;
  machine_id: string;
  cycle: number;
  timestamp: string;
  setting_1: number;
  setting_2: number;
  setting_3: number;
  sensor_values: Record<string, number>;
  is_simulated: boolean;
  stored_at: string;
}

export interface PaginatedReadings {
  machine_id: string;
  readings: ReadingRecord[];
  limit: number;
  offset: number;
  total: number;
}

export interface PaginatedPredictions {
  machine_id: string;
  predictions: PredictionRecord[];
  limit: number;
  offset: number;
  total: number;
}

export interface MachineHealthSnapshot {
  machine_id: string;
  dataset_id: string;
  health: MachineHealth;
  last_cycle: number | null;
  last_reading_at: string | null;
  latest_prediction: PredictionRecord | null;
  active_alerts: number;
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export interface AlertRecord {
  id: number;
  machine_id: string;
  alert_type: AlertType;
  severity: AlertSeverity;
  status: AlertStatus;
  prediction_id: number | null;
  model_version: string | null;
  message: string;
  created_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface AlertAcknowledgeResponse {
  alert_id: number;
  status: AlertStatus;
  acknowledged_at: string;
}

export interface AlertSummary {
  total: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  active_by_machine: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Evaluation reports (Phase 2.5, served by GET /evaluation)
// ---------------------------------------------------------------------------

export interface EvaluationLabelConfig {
  failure_horizon: number;
  rul_cap: number;
  healthy_rul_min: number;
  classification_threshold: number;
  label_definition: string;
}

export interface EvaluationResult {
  precision: number;
  recall: number;
  f1: number;
  macro_f1: number;
  roc_auc: number;
  pr_auc: number;
  confusion_matrix: { tn: number; fp: number; fn: number; tp: number };
  n_rows: number;
  n_positives: number;
}

export interface EvaluationReport {
  dataset_id: string;
  label_config: EvaluationLabelConfig;
  data: {
    train_rows: number;
    train_engines: number;
    validation_rows: number;
    validation_engines: number;
    validation_positive_ratio: number;
    official_test_rows: number;
    official_test_engines: number;
    official_test_positive_ratio: number;
  };
  models: Record<string, { validation?: EvaluationResult; test?: EvaluationResult }>;
}

export interface EvaluationIndex {
  /** Datasets that have a committed report (backend skips missing ones). */
  datasets: DatasetId[];
  /**
   * Per dataset: the Phase-2/3 default model (best supervised validation F1)
   * and ITS validation metrics — the backend returns the flat validation
   * dict of the default model, not a per-model map.
   */
  by_dataset: Record<string, { default_model: string | null; metrics: Partial<EvaluationResult> }>;
}
