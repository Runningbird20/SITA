import { apiFetch, buildQuery } from "./client";
import type {
  Alert,
  AlertMitreMapping,
  AnalysisResult,
  AnalysisTaskType,
  AlertStatus,
  Detection,
  DetectionCategory,
  DetectionDetail,
  IOC,
  IOCType,
  Incident,
  IncidentDetail,
  IncidentStatus,
  IncidentTechniqueEntry,
  MitreTechnique,
  Page,
  PipelineRunReport,
  Recommendation,
  RecommendationPriority,
  RecommendationSource,
  RecommendationStatus,
  Severity,
  ValidationStatus,
} from "./types";

const PREFIX = "/api/v1";

export interface PageParams {
  limit?: number;
  offset?: number;
  sort?: string;
}

export function fetchAlerts(
  params: PageParams & {
    severity?: Severity;
    status?: AlertStatus;
    ruleKey?: string;
    incidentId?: string;
  },
): Promise<Page<Alert>> {
  const qs = buildQuery({
    limit: params.limit,
    offset: params.offset,
    sort: params.sort,
    severity: params.severity,
    status: params.status,
    rule_key: params.ruleKey,
    incident_id: params.incidentId,
  });
  return apiFetch<Page<Alert>>(`${PREFIX}/alerts${qs}`);
}

export function fetchAlert(id: string): Promise<Alert> {
  return apiFetch<Alert>(`${PREFIX}/alerts/${id}`);
}

export function fetchAlertMitreTechniques(id: string): Promise<AlertMitreMapping[]> {
  return apiFetch<AlertMitreMapping[]>(`${PREFIX}/alerts/${id}/mitre-techniques`);
}

export function fetchIncidents(
  params: PageParams & { status?: IncidentStatus; severity?: Severity },
): Promise<Page<Incident>> {
  const qs = buildQuery({
    limit: params.limit,
    offset: params.offset,
    sort: params.sort,
    status: params.status,
    severity: params.severity,
  });
  return apiFetch<Page<Incident>>(`${PREFIX}/incidents${qs}`);
}

export function fetchIncident(id: string): Promise<IncidentDetail> {
  return apiFetch<IncidentDetail>(`${PREFIX}/incidents/${id}`);
}

export function fetchIncidentMitreTechniques(id: string): Promise<IncidentTechniqueEntry[]> {
  return apiFetch<IncidentTechniqueEntry[]>(`${PREFIX}/incidents/${id}/mitre-techniques`);
}

export function fetchIocs(
  params: PageParams & {
    iocType?: IOCType;
    validationStatus?: ValidationStatus;
    minConfidence?: number;
    search?: string;
  },
): Promise<Page<IOC>> {
  const qs = buildQuery({
    limit: params.limit,
    offset: params.offset,
    sort: params.sort,
    ioc_type: params.iocType,
    validation_status: params.validationStatus,
    min_confidence: params.minConfidence,
    search: params.search,
  });
  return apiFetch<Page<IOC>>(`${PREFIX}/iocs${qs}`);
}

export function fetchIoc(id: string): Promise<IOC> {
  return apiFetch<IOC>(`${PREFIX}/iocs/${id}`);
}

export function fetchDetections(
  params: PageParams & { category?: DetectionCategory; enabled?: boolean },
): Promise<Page<Detection>> {
  const qs = buildQuery({
    limit: params.limit,
    offset: params.offset,
    sort: params.sort,
    category: params.category,
    enabled: params.enabled,
  });
  return apiFetch<Page<Detection>>(`${PREFIX}/detections${qs}`);
}

export function fetchDetection(id: string): Promise<DetectionDetail> {
  return apiFetch<DetectionDetail>(`${PREFIX}/detections/${id}`);
}

export function fetchAnalysisResults(
  params: PageParams & { incidentId?: string; alertId?: string; taskType?: AnalysisTaskType },
): Promise<Page<AnalysisResult>> {
  const qs = buildQuery({
    limit: params.limit,
    offset: params.offset,
    sort: params.sort,
    incident_id: params.incidentId,
    alert_id: params.alertId,
    task_type: params.taskType,
  });
  return apiFetch<Page<AnalysisResult>>(`${PREFIX}/analysis-results${qs}`);
}

export function fetchRecommendations(
  params: PageParams & {
    incidentId?: string;
    alertId?: string;
    status?: RecommendationStatus;
    source?: RecommendationSource;
    priority?: RecommendationPriority;
  },
): Promise<Page<Recommendation>> {
  const qs = buildQuery({
    limit: params.limit,
    offset: params.offset,
    sort: params.sort,
    incident_id: params.incidentId,
    alert_id: params.alertId,
    status: params.status,
    source: params.source,
    priority: params.priority,
  });
  return apiFetch<Page<Recommendation>>(`${PREFIX}/recommendations${qs}`);
}

export function fetchMitreTechniques(
  params: PageParams & { tactic?: string },
): Promise<Page<MitreTechnique>> {
  const qs = buildQuery({
    limit: params.limit,
    offset: params.offset,
    sort: params.sort,
    tactic: params.tactic,
  });
  return apiFetch<Page<MitreTechnique>>(`${PREFIX}/mitre-techniques${qs}`);
}

export function runPipeline(since?: string): Promise<PipelineRunReport> {
  return apiFetch<PipelineRunReport>(`${PREFIX}/pipeline/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ since: since ?? null }),
  });
}
