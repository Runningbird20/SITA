import { useState } from "react";
import { Pagination } from "../components/ui/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/QueryState";
import { useApiQuery } from "../hooks/useApiQuery";
import { fetchIocs } from "../api/resources";
import type { IOCType, ValidationStatus } from "../api/types";
import "../styles/dashboard.css";

const LIMIT = 25;

export function IocsPage() {
  const [search, setSearch] = useState("");
  const [iocType, setIocType] = useState<IOCType | "">("");
  const [validationStatus, setValidationStatus] = useState<ValidationStatus | "">("");
  const [offset, setOffset] = useState(0);

  const query = useApiQuery(
    () =>
      fetchIocs({
        limit: LIMIT,
        offset,
        sort: "-last_seen",
        search: search || undefined,
        iocType: iocType || undefined,
        validationStatus: validationStatus || undefined,
      }),
    [search, iocType, validationStatus, offset],
  );

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>IOCs</h1>
          <p>Extracted, validated indicators of compromise.</p>
        </div>
      </div>

      <div className="filter-bar">
        <input
          type="text"
          placeholder="Search value…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
        />
        <select
          value={iocType}
          onChange={(e) => {
            setIocType(e.target.value as IOCType | "");
            setOffset(0);
          }}
        >
          <option value="">All types</option>
          <option value="ipv4">IPv4</option>
          <option value="ipv6">IPv6</option>
          <option value="domain">Domain</option>
          <option value="url">URL</option>
          <option value="file_hash_md5">MD5</option>
          <option value="file_hash_sha1">SHA1</option>
          <option value="file_hash_sha256">SHA256</option>
          <option value="email">Email</option>
          <option value="username">Username</option>
        </select>
        <select
          value={validationStatus}
          onChange={(e) => {
            setValidationStatus(e.target.value as ValidationStatus | "");
            setOffset(0);
          }}
        >
          <option value="">All validation statuses</option>
          <option value="valid">Valid</option>
          <option value="invalid">Invalid</option>
          <option value="unverified">Unverified</option>
        </select>
      </div>

      {query.loading && <LoadingState label="Loading IOCs…" />}
      {!query.loading && query.error && (
        <ErrorState message={query.error} onRetry={query.refetch} />
      )}
      {!query.loading && !query.error && query.data && query.data.items.length === 0 && (
        <EmptyState message="No IOCs match these filters." />
      )}
      {!query.loading && !query.error && query.data && query.data.items.length > 0 && (
        <div className="panel">
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Value</th>
                <th>Confidence</th>
                <th>Validation</th>
                <th>Linked to</th>
                <th>Last seen</th>
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((ioc) => (
                <tr key={ioc.id}>
                  <td className="mono">{ioc.ioc_type}</td>
                  <td className="mono">{ioc.value}</td>
                  <td className="mono">{ioc.confidence.toFixed(2)}</td>
                  <td>{ioc.validation_status}</td>
                  <td className="mono">
                    {ioc.alert_ids.length} alert{ioc.alert_ids.length === 1 ? "" : "s"},{" "}
                    {ioc.event_ids.length} event{ioc.event_ids.length === 1 ? "" : "s"}
                  </td>
                  <td className="mono">{new Date(ioc.last_seen).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination
            total={query.data.total}
            limit={LIMIT}
            offset={offset}
            onOffsetChange={setOffset}
          />
        </div>
      )}
    </div>
  );
}
