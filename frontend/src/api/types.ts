// Hand-mirrors backend/app/schemas/*.py — see DEF.md § Phase 10 for why
// this is hand-written rather than generated from the OpenAPI schema.

export type Severity = "low" | "medium" | "high" | "critical";
export type SourceType = "auth" | "endpoint" | "network" | "dns" | "web";
export type AlertStatus = "new" | "investigating" | "resolved" | "false_positive";
export type IncidentStatus = "open" | "investigating" | "contained" | "closed";
export type IOCType =
  | "ipv4"
  | "ipv6"
  | "domain"
  | "url"
  | "file_hash_md5"
  | "file_hash_sha1"
  | "file_hash_sha256"
  | "email"
  | "username";
export type ExtractionSource = "regex" | "llm_assisted";
export type ValidationStatus = "valid" | "invalid" | "unverified";
export type EntityType = "host" | "user" | "ip" | "domain";
export type DetectionCategory = "authentication" | "network" | "endpoint" | "web";
export type MitreMappingSource = "rule" | "llm";
export type AnalysisTaskType =
  | "incident_summary"
  | "severity_explanation"
  | "attack_classification"
  | "investigation_hypothesis"
  | "investigation_steps"
  | "mitre_suggestion";
export type AnalysisValidationStatus = "valid" | "invalid" | "timeout" | "provider_error";
export type RecommendationSource = "rule_based" | "llm";
export type RecommendationPriority = "low" | "medium" | "high";
export type RecommendationStatus = "open" | "acknowledged" | "dismissed" | "completed";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: unknown;
  };
}

export interface SecurityEvent {
  id: string;
  source_type: SourceType;
  occurred_at: string;
  ingested_at: string;
  source_host: string | null;
  raw_payload: Record<string, unknown>;
  normalized: Record<string, unknown>;
  ingestion_batch_id: string | null;
  created_at: string;
}

export interface Alert {
  id: string;
  detection_id: string;
  incident_id: string | null;
  severity: Severity;
  confidence: number;
  status: AlertStatus;
  rationale: string;
  severity_factors: Record<string, unknown>;
  first_event_at: string;
  last_event_at: string;
  created_at: string;
  updated_at: string;
}

export interface Incident {
  id: string;
  title: string;
  status: IncidentStatus;
  severity: Severity;
  first_activity_at: string;
  last_activity_at: string;
  correlation_method: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  alert_count: number;
}

export interface IOC {
  id: string;
  ioc_type: IOCType;
  value: string;
  extraction_source: ExtractionSource;
  validation_status: ValidationStatus;
  confidence: number;
  first_seen: string;
  last_seen: string;
  created_at: string;
  updated_at: string;
  alert_ids: string[];
  event_ids: string[];
}

export interface Entity {
  id: string;
  entity_type: EntityType;
  identifier: string;
  first_seen: string;
  last_seen: string;
  entity_metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface Detection {
  id: string;
  rule_key: string;
  name: string;
  description: string;
  category: DetectionCategory;
  default_severity: Severity;
  enabled: boolean;
  config: Record<string, unknown> | null;
  created_at: string;
}

export interface MitreTechnique {
  id: string;
  technique_id: string;
  name: string;
  tactic: string;
  description: string;
  dataset_version: string;
}

export interface DetectionDetail extends Detection {
  mitre_techniques: MitreTechnique[];
}

export interface AlertMitreMapping {
  technique: MitreTechnique;
  source: MitreMappingSource;
  analysis_result_id: string | null;
}

export interface TechniqueEvidence {
  alert_id: string;
  source: MitreMappingSource;
  analysis_result_id: string | null;
  confidence: number | null;
}

export interface IncidentTechniqueEntry {
  technique_id: string;
  name: string;
  tactic: string;
  evidence: TechniqueEvidence[];
  sources: MitreMappingSource[];
}

export type FeedbackRating = "up" | "down";

export interface AnalysisFeedback {
  id: string;
  analysis_result_id: string;
  rating: FeedbackRating;
  created_at: string;
  updated_at: string;
}

export interface AnalysisResult {
  id: string;
  incident_id: string | null;
  alert_id: string | null;
  task_type: AnalysisTaskType;
  provider: string;
  model: string;
  prompt_version: string;
  raw_output: string;
  parsed_output: Record<string, unknown> | null;
  validation_status: AnalysisValidationStatus;
  confidence: number | null;
  latency_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  grounding_retry_used: boolean;
  feedback: AnalysisFeedback | null;
  created_at: string;
}

export interface Recommendation {
  id: string;
  incident_id: string | null;
  alert_id: string | null;
  source: RecommendationSource;
  analysis_result_id: string | null;
  text: string;
  priority: RecommendationPriority;
  status: RecommendationStatus;
  created_at: string;
  updated_at: string;
}

export interface IncidentDetail extends Incident {
  alerts: Alert[];
  iocs: IOC[];
  entities: Entity[];
  analysis_results: AnalysisResult[];
  recommendations: Recommendation[];
  mitre_techniques: IncidentTechniqueEntry[];
}

export interface DetectionRunReport {
  since: string | null;
  rules_run: number;
  alerts_created: number;
  alerts_by_rule: Record<string, number>;
}

export interface IOCExtractionReport {
  since: string | null;
  events_scanned: number;
  iocs_created: number;
  iocs_updated: number;
  event_links_created: number;
  alert_links_created: number;
  iocs_by_type: Record<string, number>;
}

export interface MitreMappingReport {
  since: string | null;
  detection_technique_links_created: number;
  alerts_processed: number;
  alert_technique_mappings_created: number;
}

export interface CorrelationRunReport {
  since: string | null;
  alerts_processed: number;
  incidents_created: number;
  incidents_joined: number;
  host_entities_created: number;
  host_links_created: number;
}

export interface TriageRunReport {
  since: string | null;
  incidents_processed: number;
  analysis_results_created: number;
  analysis_results_skipped: number;
  recommendations_created: number;
  mitre_mappings_created: number;
  by_task_type: Record<string, number>;
}

export interface PipelineRunReport {
  since: string | null;
  detection: DetectionRunReport;
  ioc: IOCExtractionReport;
  mitre: MitreMappingReport;
  correlation: CorrelationRunReport;
  triage: TriageRunReport;
}
