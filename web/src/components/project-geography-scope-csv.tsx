"use client";

import { ChangeEvent, useState } from "react";
import {
  projectsApi,
  type ProjectGeographyScopeImportPreview,
} from "@/lib/api";

interface ProjectGeographyScopeCsvProps {
  projectId: string;
  disabled?: boolean;
  onUseAcceptedCodes: (codes: string[]) => void;
}

const MAX_CSV_BYTES = 2 * 1024 * 1024;

function parseVillageCodes(csvText: string): string[] {
  const lines = csvText
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (!lines.length) {
    throw new Error("The CSV file is empty.");
  }

  const header = lines[0]
    .split(",")[0]
    .trim()
    .replace(/^"|"$/g, "")
    .toLocaleLowerCase();

  if (
    header !== "village_lgd_code" &&
    header !== "lgd_code"
  ) {
    throw new Error(
      "The first CSV column must be village_lgd_code or lgd_code.",
    );
  }

  return lines.slice(1).map((line) =>
    line
      .split(",")[0]
      .trim()
      .replace(/^"|"$/g, ""),
  );
}

function CodeList({
  label,
  codes,
}: {
  label: string;
  codes: string[];
}) {
  if (!codes.length) return null;

  return (
    <div className="rounded border border-amber-200 bg-amber-50 p-3">
      <p className="text-xs font-semibold text-amber-900">
        {label} ({codes.length})
      </p>
      <p className="mt-1 break-words font-mono text-xs text-amber-800">
        {codes.join(", ")}
      </p>
    </div>
  );
}

export function ProjectGeographyScopeCsv({
  projectId,
  disabled = false,
  onUseAcceptedCodes,
}: ProjectGeographyScopeCsvProps) {
  const [preview, setPreview] =
    useState<ProjectGeographyScopeImportPreview | null>(null);
  const [fileName, setFileName] = useState("");
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  const previewFile = async (
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) return;

    setPreview(null);
    setFileName(file.name);
    setError("");

    if (file.size > MAX_CSV_BYTES) {
      setError("CSV files must be 2 MB or smaller.");
      return;
    }

    try {
      const codes = parseVillageCodes(await file.text());
      if (!codes.length) {
        throw new Error(
          "The CSV contains no village LGD-code rows.",
        );
      }

      setLoading(true);
      setPreview(
        await projectsApi.previewGeographyScopeImport(
          projectId,
          codes,
        ),
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to preview geography CSV",
      );
    } finally {
      setLoading(false);
    }
  };

  const downloadScope = async () => {
    setDownloading(true);
    setError("");
    try {
      await projectsApi.downloadGeographyScopeCsv(projectId);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to export geography scope",
      );
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div
      aria-label="Project geography CSV tools"
      className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-3"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h5 className="text-sm font-semibold text-blue-950">
            CSV import and export
          </h5>
          <p className="mt-1 text-xs text-blue-800">
            Preview validates the file without changing the project.
            Accepted villages are loaded into the picker and still
            require the audited Save geography scope action.
          </p>
        </div>

        <button
          type="button"
          disabled={disabled || downloading}
          onClick={() => void downloadScope()}
          className="rounded border border-blue-300 bg-white px-3 py-2 text-xs font-semibold text-blue-800 disabled:opacity-50"
        >
          {downloading ? "Exporting…" : "Export current scope CSV"}
        </button>
      </div>

      <label className="mt-3 block text-xs font-semibold text-blue-950">
        Import village scope CSV
        <input
          type="file"
          accept=".csv,text/csv"
          disabled={disabled || loading}
          onChange={(event) => void previewFile(event)}
          className="mt-1 block w-full rounded border border-blue-200 bg-white px-3 py-2 text-xs"
        />
      </label>

      <p className="mt-1 text-[11px] text-blue-700">
        Required first column: village_lgd_code. Maximum 500
        unique villages and 2 MB per file.
      </p>

      {loading ? (
        <p className="mt-3 text-xs text-blue-800">
          Validating {fileName}…
        </p>
      ) : null}

      {error ? (
        <p className="mt-3 text-xs font-medium text-red-700">
          {error}
        </p>
      ) : null}

      {preview ? (
        <div className="mt-3 space-y-3">
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="rounded bg-white p-3">
              <p className="text-[11px] uppercase text-gray-500">
                Input rows
              </p>
              <p className="text-lg font-semibold">
                {preview.summary.input_row_count}
              </p>
            </div>
            <div className="rounded bg-white p-3">
              <p className="text-[11px] uppercase text-gray-500">
                Accepted
              </p>
              <p className="text-lg font-semibold text-green-700">
                {preview.summary.accepted_count}
              </p>
            </div>
            <div className="rounded bg-white p-3">
              <p className="text-[11px] uppercase text-gray-500">
                Rejected
              </p>
              <p className="text-lg font-semibold text-red-700">
                {preview.summary.invalid_count +
                  preview.summary.unknown_count}
              </p>
            </div>
          </div>

          <CodeList
            label="Duplicate codes ignored"
            codes={preview.duplicate_village_lgd_codes}
          />
          <CodeList
            label="Malformed codes"
            codes={preview.invalid_village_lgd_codes}
          />
          <CodeList
            label="Unknown canonical villages"
            codes={preview.unknown_village_lgd_codes}
          />

          {preview.summary.limit_exceeded ? (
            <p className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-800">
              The import exceeds the 500-village project limit.
            </p>
          ) : null}

          {preview.accepted_villages.length ? (
            <div className="max-h-48 overflow-auto rounded border bg-white">
              <table className="min-w-full divide-y text-xs">
                <thead className="sticky top-0 bg-gray-50 text-left text-gray-600">
                  <tr>
                    <th className="px-3 py-2">Village</th>
                    <th className="px-3 py-2">LGD</th>
                    <th className="px-3 py-2">Hierarchy</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {preview.accepted_villages.map((village) => (
                    <tr key={village.village_lgd_code}>
                      <td className="px-3 py-2 font-medium">
                        {village.village_name}
                      </td>
                      <td className="px-3 py-2 font-mono">
                        {village.village_lgd_code}
                      </td>
                      <td className="px-3 py-2 text-gray-600">
                        {village.state_name} /{" "}
                        {village.district_name} /{" "}
                        {village.block_name}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          <button
            type="button"
            disabled={disabled || !preview.summary.can_apply}
            onClick={() =>
              onUseAcceptedCodes(
                preview.normalized_village_lgd_codes,
              )
            }
            className="rounded bg-blue-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
          >
            Use {preview.summary.accepted_count} accepted villages
          </button>

          <p className="text-[11px] text-blue-700">
            Preview performed no database write. Candidate activation,
            promotion, runtime eligibility, and Android behavior are
            unchanged.
          </p>
        </div>
      ) : null}
    </div>
  );
}
