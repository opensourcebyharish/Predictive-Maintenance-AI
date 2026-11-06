/**
 * Synthetic API payloads mirroring the FastAPI Pydantic schemas
 * (see src/predictive_maintenance/api/schemas.py). Every value is fake but
 * structurally faithful so component tests exercise real parsing logic.
 */

import type {
  AlertRecord,
  ApiHealth,
  ApiReadiness,
  DatasetId,
  EvaluationIndex,
  EvaluationReport,
  MachineDetail,
  MachineHealthSnapshot,
  MachineSummary,
  PaginatedReadings,
  PredictionRecord,
} from "@/api/types";

export const MACHINE_IDS = ["SIM-001", "SIM-002", "SIM-003"] as const;

export const HEALTH_OK: ApiHealth = {
  status: "ok",
  app: "predictive-maintenance-ai",
  version: "0.2.0",
  service_loaded: true,
};

export const READINESS_OK: ApiReadiness = {
  ready: true,
  datasets: Object.fromEntries(
    [
      ["FD001", "random_forest"],
      ["FD002", "random_forest"],
      ["FD003", "xgboost"],
      ["FD004", "xgboost"],
    ].map(([dataset, model]) => [
      dataset,
      {
        ready: true,
        default_model: model,
        models: { isolation_forest: "loaded", random_forest: "loaded", xgboost: "loaded" },
        error: null,
      },
    ]),
  ),
};

export const MACHINES: MachineSummary[] = [
  {
    machine_id: "SIM-001",
    dataset_id: "FD001",
    reading_count: 30,
    first_cycle: 1,
    last_cycle: 30,
    latest_reading_at: "2026-01-01T00:30:00.000Z",
    health: "healthy",
  },
  {
    machine_id: "SIM-002",
    dataset_id: "FD001",
    reading_count: 30,
    first_cycle: 1,
    last_cycle: 30,
    latest_reading_at: "2026-01-01T00:30:00.000Z",
    health: "elevated_risk",
  },
  {
    machine_id: "SIM-003",
    dataset_id: "FD003",
    reading_count: 30,
    first_cycle: 1,
    last_cycle: 30,
    latest_reading_at: "2026-01-01T00:30:00.000Z",
    health: "critical_risk",
  },
];

/** s-value generators keep sensor grid + charts populated in tests. */
function sensorValue(sensor: string, cycle: number, machine: string): number {
  const index = Number(sensor.slice(1));
  const base = machine === "SIM-003" ? 900 : 500;
  return base + index * 10 + cycle * (index % 5);
}

export function buildReadings(machineId: string, count = 30): PaginatedReadings["readings"] {
  return Array.from({ length: count }, (_, i) => {
    const cycle = i + 1;
    const values: Record<string, number> = {};
    for (let s = 1; s <= 21; s += 1) values[`s${s}`] = sensorValue(`s${s}`, cycle, machineId);
    return {
      id: cycle,
      machine_id: machineId,
      cycle,
      timestamp: new Date(Date.UTC(2026, 0, 1, 0, cycle % 60, 0)).toISOString(),
      setting_1: 10 + (cycle % 5) * 0.1,
      setting_2: 0.25,
      setting_3: 100,
      sensor_values: values,
      is_simulated: machineId.startsWith("SIM-"),
      stored_at: new Date(Date.UTC(2026, 0, 1, 0, cycle % 60, 5)).toISOString(),
    };
  });
}

export function buildPredictions(machineId: string, count = 30): PredictionRecord[] {
  const failureProb = machineId === "SIM-003" ? 0.85 : machineId === "SIM-002" ? 0.55 : 0.15;
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    reading_id: i + 1,
    machine_id: machineId,
    model: "random_forest",
    model_version: `${machineId === "SIM-003" ? "FD003" : "FD001"}:random_forest@fixtures0001`,
    predicted_at: new Date(Date.UTC(2026, 0, 1, 0, 1 + i, 10)).toISOString(),
    anomaly_score: failureProb - 0.1 + i * 0.002,
    anomaly_status: machineId !== "SIM-001",
    failure_probability: failureProb + i * 0.001,
    failure_status: failureProb >= 0.5,
  }));
}

export const PREDICTION_LATEST: PredictionRecord = buildPredictions("SIM-001", 30)[29];

export const MACHINE_DETAILS: Record<string, MachineDetail> = Object.fromEntries(
  MACHINES.map((machine) => {
    const predictions = buildPredictions(machine.machine_id);
    return [
      machine.machine_id,
      {
        ...machine,
        latest_sensor_values: buildReadings(machine.machine_id, 1)[0].sensor_values,
        latest_prediction: predictions[predictions.length - 1],
        active_alerts: machine.machine_id === "SIM-001" ? 1 : machine.machine_id === "SIM-003" ? 1 : 0,
      } satisfies MachineDetail,
    ];
  }),
);

export const MACHINE_HEALTH_SNAPSHOTS: Record<string, MachineHealthSnapshot> = Object.fromEntries(
  MACHINES.map((machine) => [
    machine.machine_id,
    {
      machine_id: machine.machine_id,
      dataset_id: machine.dataset_id,
      health: machine.health,
      last_cycle: machine.last_cycle,
      last_reading_at: machine.latest_reading_at,
      latest_prediction: MACHINE_DETAILS[machine.machine_id].latest_prediction,
      active_alerts: MACHINE_DETAILS[machine.machine_id].active_alerts,
    } satisfies MachineHealthSnapshot,
  ]),
);

export const ALERTS: AlertRecord[] = [
  {
    id: 2,
    machine_id: "SIM-003",
    alert_type: "critical_failure_risk",
    severity: "critical",
    status: "active",
    prediction_id: 30,
    model_version: "FD003:xgboost@fixtures0001",
    message: "Failure probability 0.851 exceeds critical threshold 0.8",
    created_at: "2026-01-01T00:30:10.000Z",
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
  },
  {
    id: 1,
    machine_id: "SIM-001",
    alert_type: "anomaly_detected",
    severity: "medium",
    status: "active",
    prediction_id: 29,
    model_version: "FD001:random_forest@fixtures0001",
    message: "Anomaly detected (score=0.251) using random_forest",
    created_at: "2026-01-01T00:29:10.000Z",
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
  },
  {
    id: 3,
    machine_id: "SIM-002",
    alert_type: "elevated_failure_risk",
    severity: "high",
    status: "acknowledged",
    prediction_id: 30,
    model_version: "FD001:random_forest@fixtures0001",
    message: "Failure probability 0.552 exceeds elevated threshold 0.5",
    created_at: "2026-01-01T00:30:10.000Z",
    acknowledged_at: "2026-01-01T00:35:00.000Z",
    acknowledged_by: "operator",
    resolved_at: null,
    resolved_by: null,
  },
  {
    id: 4,
    machine_id: "SIM-002",
    alert_type: "machine_recovered",
    severity: "low",
    status: "resolved",
    prediction_id: null,
    model_version: null,
    message: "Machine returned to healthy state",
    created_at: "2026-01-01T00:20:10.000Z",
    acknowledged_at: "2026-01-01T00:21:00.000Z",
    acknowledged_by: "operator",
    resolved_at: "2026-01-01T00:25:00.000Z",
    resolved_by: "alert_engine",
  },
];

export const ALERT_SUMMARY_OK = {
  total: ALERTS.length,
  by_status: { active: 2, acknowledged: 1, resolved: 1 },
  by_type: {
    anomaly_detected: 1,
    elevated_failure_risk: 1,
    critical_failure_risk: 1,
    machine_recovered: 1,
  },
  by_severity: { medium: 1, high: 1, critical: 1, low: 1 },
  active_by_machine: { "SIM-001": 1, "SIM-003": 1 },
};

/**
 * Phase 2.5 evaluation reports. `eval_FD001.json` is stored verbatim; the
 * other three datasets are synthesized with the same shape and dataset-specific
 * headline numbers (both supervised models, like the real reports which train
 * random_forest and xgboost per subset).
 */
export const EVALUATION_REPORT_FD001: EvaluationReport = {
  dataset_id: "FD001",
  label_config: {
    failure_horizon: 30,
    rul_cap: 130,
    healthy_rul_min: 50,
    classification_threshold: 0.5,
    label_definition: "failure_within_30: engine fails within 30 cycles (uncapped truth)",
  },
  data: {
    train_rows: 16779,
    train_engines: 80,
    validation_rows: 3852,
    validation_engines: 20,
    validation_positive_ratio: 0.161,
    official_test_rows: 13096,
    official_test_engines: 100,
    official_test_positive_ratio: 0.025,
  },
  models: {
    random_forest: {
      validation: {
        precision: 0.77,
        recall: 0.86,
        f1: 0.81,
        macro_f1: 0.85,
        roc_auc: 0.88,
        pr_auc: 0.79,
        confusion_matrix: { tn: 2900, fp: 320, fn: 85, tp: 547 },
        n_rows: 3852,
        n_positives: 620,
      },
      test: {
        precision: 0.4,
        recall: 0.72,
        f1: 0.51,
        macro_f1: 0.69,
        roc_auc: 0.82,
        pr_auc: 0.45,
        confusion_matrix: { tn: 12300, fp: 420, fn: 70, tp: 180 },
        n_rows: 13096,
        n_positives: 250,
      },
    },
  },
};

/** One supervised model's split metrics as embedded in a report file. */
interface SupervisedModel {
  validation: NonNullable<EvaluationReport["models"]["random_forest"]["validation"]>;
  test: NonNullable<EvaluationReport["models"]["random_forest"]["test"]>;
}

interface DatasetReportSpec {
  data: EvaluationReport["data"];
  random_forest: SupervisedModel;
  xgboost: SupervisedModel;
}

const COMMON_LABEL_CONFIG: EvaluationReport["label_config"] = {
  failure_horizon: 30,
  rul_cap: 130,
  healthy_rul_min: 50,
  classification_threshold: 0.5,
  label_definition: "failure_within_30: engine fails within 30 cycles (uncapped truth)",
};

function buildReport(datasetId: DatasetId, spec: DatasetReportSpec): EvaluationReport {
  return {
    dataset_id: datasetId,
    label_config: COMMON_LABEL_CONFIG,
    data: spec.data,
    models: {
      random_forest: spec.random_forest,
      xgboost: spec.xgboost,
    },
  };
}

export const EVALUATION_REPORTS: Record<DatasetId, EvaluationReport> = {
  FD001: EVALUATION_REPORT_FD001,
  FD002: buildReport("FD002", {
    data: {
      train_rows: 40530,
      train_engines: 532,
      validation_rows: 6093,
      validation_engines: 80,
      validation_positive_ratio: 0.32,
      official_test_rows: 12946,
      official_test_engines: 259,
      official_test_positive_ratio: 0.118,
    },
    random_forest: {
      validation: {
        precision: 0.67, recall: 0.79, f1: 0.72, macro_f1: 0.79, roc_auc: 0.81, pr_auc: 0.68,
        confusion_matrix: { tn: 3500, fp: 640, fn: 470, tp: 1483 },
        n_rows: 6093, n_positives: 1953,
      },
      test: {
        precision: 0.3, recall: 0.55, f1: 0.39, macro_f1: 0.58, roc_auc: 0.71, pr_auc: 0.22,
        confusion_matrix: { tn: 10500, fp: 940, fn: 640, tp: 866 },
        n_rows: 12946, n_positives: 1528,
      },
    },
    xgboost: {
      validation: {
        precision: 0.64, recall: 0.76, f1: 0.69, macro_f1: 0.76, roc_auc: 0.79, pr_auc: 0.64,
        confusion_matrix: { tn: 3410, fp: 690, fn: 462, tp: 1531 },
        n_rows: 6093, n_positives: 1953,
      },
      test: {
        precision: 0.27, recall: 0.51, f1: 0.35, macro_f1: 0.55, roc_auc: 0.69, pr_auc: 0.2,
        confusion_matrix: { tn: 10330, fp: 980, fn: 700, tp: 936 },
        n_rows: 12946, n_positives: 1528,
      },
    },
  }),
  FD003: buildReport("FD003", {
    data: {
      train_rows: 16018,
      train_engines: 80,
      validation_rows: 3700,
      validation_engines: 20,
      validation_positive_ratio: 0.213,
      official_test_rows: 13089,
      official_test_engines: 100,
      official_test_positive_ratio: 0.04,
    },
    random_forest: {
      validation: {
        precision: 0.78, recall: 0.86, f1: 0.83, macro_f1: 0.86, roc_auc: 0.89, pr_auc: 0.81,
        confusion_matrix: { tn: 2680, fp: 260, fn: 132, tp: 798 },
        n_rows: 3700, n_positives: 788,
      },
      test: {
        precision: 0.38, recall: 0.7, f1: 0.49, macro_f1: 0.67, roc_auc: 0.8, pr_auc: 0.42,
        confusion_matrix: { tn: 12100, fp: 500, fn: 90, tp: 210 },
        n_rows: 13089, n_positives: 477,
      },
    },
    xgboost: {
      validation: {
        precision: 0.8, recall: 0.88, f1: 0.84, macro_f1: 0.88, roc_auc: 0.9, pr_auc: 0.83,
        confusion_matrix: { tn: 2740, fp: 240, fn: 106, tp: 824 },
        n_rows: 3700, n_positives: 788,
      },
      test: {
        precision: 0.45, recall: 0.76, f1: 0.57, macro_f1: 0.73, roc_auc: 0.84, pr_auc: 0.52,
        confusion_matrix: { tn: 12200, fp: 400, fn: 60, tp: 240 },
        n_rows: 13089, n_positives: 477,
      },
    },
  }),
  FD004: buildReport("FD004", {
    data: {
      train_rows: 19830,
      train_engines: 249,
      validation_rows: 3705,
      validation_engines: 49,
      validation_positive_ratio: 0.285,
      official_test_rows: 13200,
      official_test_engines: 248,
      official_test_positive_ratio: 0.09,
    },
    random_forest: {
      validation: {
        precision: 0.63, recall: 0.72, f1: 0.67, macro_f1: 0.72, roc_auc: 0.74, pr_auc: 0.61,
        confusion_matrix: { tn: 2100, fp: 600, fn: 560, tp: 1500 },
        n_rows: 3705, n_positives: 1056,
      },
      test: {
        precision: 0.22, recall: 0.44, f1: 0.29, macro_f1: 0.48, roc_auc: 0.61, pr_auc: 0.13,
        confusion_matrix: { tn: 10200, fp: 1200, fn: 850, tp: 560 },
        n_rows: 13200, n_positives: 1188,
      },
    },
    xgboost: {
      validation: {
        precision: 0.66, recall: 0.75, f1: 0.7, macro_f1: 0.74, roc_auc: 0.78, pr_auc: 0.66,
        confusion_matrix: { tn: 2140, fp: 570, fn: 540, tp: 1530 },
        n_rows: 3705, n_positives: 1056,
      },
      test: {
        precision: 0.26, recall: 0.5, f1: 0.34, macro_f1: 0.53, roc_auc: 0.66, pr_auc: 0.19,
        confusion_matrix: { tn: 10350, fp: 1150, fn: 700, tp: 700 },
        n_rows: 13200, n_positives: 1188,
      },
    },
  }),
};

interface ReportModelBlock {
  validation?: NonNullable<EvaluationReport["models"]["random_forest"]["validation"]>;
}

/** Non-null accessor backing the index fixture: the backend always embeds the
 * default model's validation metrics, so the fixtures must too. */
function validationOf(
  model: ReportModelBlock,
): NonNullable<EvaluationReport["models"]["random_forest"]["validation"]> {
  if (model.validation === undefined) {
    throw new Error("fixture evaluation reports must embed validation metrics");
  }
  return model.validation;
}

/**
 * GET /evaluation contract (see src/predictive_maintenance/api/routes/evaluation.py):
 * per dataset the default model name plus the FLAT validation metrics dict of
 * that model — not a map keyed by model name.
 */
export const EVALUATION_INDEX_FIXTURE: EvaluationIndex = {
  datasets: ["FD001", "FD002", "FD003", "FD004"],
  by_dataset: {
    FD001: {
      default_model: "random_forest",
      metrics: validationOf(EVALUATION_REPORTS.FD001.models.random_forest),
    },
    FD002: {
      default_model: "random_forest",
      metrics: validationOf(EVALUATION_REPORTS.FD002.models.random_forest),
    },
    FD003: {
      default_model: "xgboost",
      metrics: validationOf(EVALUATION_REPORTS.FD003.models.xgboost),
    },
    FD004: {
      default_model: "xgboost",
      metrics: validationOf(EVALUATION_REPORTS.FD004.models.xgboost),
    },
  },
};
