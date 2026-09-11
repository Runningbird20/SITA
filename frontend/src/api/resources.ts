import { apiFetch, buildQuery } from "./client";
import type {
  Alert,
  AlertMitreMapping,
  AnalysisFeedback,
  AnalysisResult,
  AnalysisTaskType,
  AlertStatus,
  AuditLogEntry,
  ChatMessage,
  Detection,
  DetectionCategory,
  DetectionDetail,
  FeedbackRating,
  IOC,
  IOCType,
  Incident,
  IncidentDetail,
  IncidentStatus,
  IncidentTechniqueEntry,
  LoginResponse,
  MitreTechnique,
  Page,
  PipelineJob,
  Recommendation,
  RecommendationPriority,
  RecommendationSource,
  RecommendationStatus,
  Severity,
  TuningSuggestion,
  User,
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

export function setAlertStatus(id: string, status: AlertStatus): Promise<Alert> {
  return apiFetch<Alert>(`${PREFIX}/alerts/${id}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
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

/** Full conversation thread for one incident, oldest first — see DEF.md
 * § Phase 7, "Post-roadmap addition: a conversational interface with an
 * incident".
 */
export function fetchIncidentChat(incidentId: string): Promise<ChatMessage[]> {
  return apiFetch<ChatMessage[]>(`${PREFIX}/incidents/${incidentId}/chat`);
}

/** Asks a follow-up question about this incident; returns only the
 * assistant's reply (the caller already knows what it just asked).
 */
export function postIncidentChatMessage(incidentId: string, message: string): Promise<ChatMessage> {
  return apiFetch<ChatMessage>(`${PREFIX}/incidents/${incidentId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
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

/** Deterministic, advisory-only suggestions computed from analyst
 * false-positive feedback — see DEF.md § Phase 7, "Post-roadmap addition:
 * rule tuning suggestions from analyst feedback". Applying one is a
 * separate, explicit action via updateDetectionConfig.
 */
export function fetchTuningSuggestions(): Promise<TuningSuggestion[]> {
  return apiFetch<TuningSuggestion[]>(`${PREFIX}/detections/tuning-suggestions`);
}

export function updateDetectionConfig(
  id: string,
  config: Record<string, unknown>,
): Promise<Detection> {
  return apiFetch<Detection>(`${PREFIX}/detections/${id}/config`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
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

export function setAnalysisFeedback(
  analysisResultId: string,
  rating: FeedbackRating,
): Promise<AnalysisFeedback> {
  return apiFetch<AnalysisFeedback>(`${PREFIX}/analysis-results/${analysisResultId}/feedback`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating }),
  });
}

export function clearAnalysisFeedback(analysisResultId: string): Promise<void> {
  return apiFetch<void>(`${PREFIX}/analysis-results/${analysisResultId}/feedback`, {
    method: "DELETE",
  });
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

/** Schedules the full pipeline as a background job and returns
 * immediately — the job starts out "pending"/"running" with no `result`
 * yet. Poll `getPipelineJob` for progress and the eventual report. See
 * DEF.md § Phase 9, "Post-roadmap addition: background pipeline jobs".
 */
export function runPipeline(since?: string): Promise<PipelineJob> {
  return apiFetch<PipelineJob>(`${PREFIX}/pipeline/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ since: since ?? null }),
  });
}

/** Force-regenerates AI triage only (every task, even for incidents that
 * already have a result) — distinct from runPipeline, which skips triage
 * for anything already done. Also scheduled as a background job — see
 * DEF.md § Phase 9, "Reanalyze (post-roadmap)" and "Post-roadmap
 * addition: background pipeline jobs".
 */
export function reanalyze(since?: string): Promise<PipelineJob> {
  return apiFetch<PipelineJob>(`${PREFIX}/pipeline/reanalyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ since: since ?? null }),
  });
}

export function fetchPipelineJob(jobId: string): Promise<PipelineJob> {
  return apiFetch<PipelineJob>(`${PREFIX}/pipeline/jobs/${jobId}`);
}

export function fetchMe(): Promise<User | null> {
  return apiFetch<User | null>(`${PREFIX}/auth/me`);
}

export function login(username: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>(`${PREFIX}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<void> {
  return apiFetch<void>(`${PREFIX}/auth/logout`, { method: "POST" });
}

export function fetchAuditLog(
  params: PageParams & { userId?: string; action?: string },
): Promise<Page<AuditLogEntry>> {
  const qs = buildQuery({
    limit: params.limit,
    offset: params.offset,
    sort: params.sort,
    user_id: params.userId,
    action: params.action,
  });
  return apiFetch<Page<AuditLogEntry>>(`${PREFIX}/audit-log${qs}`);
}
