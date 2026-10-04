"use client";

import { useState } from "react";
import { api } from "@/lib/api";

type Candidate = {
  source_feature_id: string;
  source_vlcode: string | null;
  source_state_name: string | null;
  source_district_name: string | null;
  source_block_name: string | null;
  source_village_name: string | null;
  eligible_for_project_local_addition: boolean;
};

export default function ProjectLocalVillageAuthorization({
  projectId,
  candidate,
  pinCodes,
  onAuthorized,
}: {
  projectId: string;
  candidate: Candidate | null;
  pinCodes: string[];
  onAuthorized: () => void;
}) {
  const [reason, setReason] = useState(
    "Project administrator confirms the parent match and project-local village."
  );
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!candidate?.eligible_for_project_local_addition) return null;
  const selectedCandidate = candidate;

  async function authorize() {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api<{
        status: string;
        parent_matches: Record<string, boolean>;
      }>(
        `/api/v1/master-data/geography/project-village-resolutions/projects/${projectId}/local-additions`,
        {
          method: "POST",
          body: {
            nwdp_source_feature_id: selectedCandidate.source_feature_id,
            display_name:
              selectedCandidate.source_village_name ||
              selectedCandidate.source_vlcode ||
              "Project-local village",
            pin_codes: pinCodes,
            reason,
            rollback_token: `project-local-${selectedCandidate.source_feature_id.slice(0, 12)}`,
            confirmation_phrase: confirmation,
          },
        }
      );
      const matched = Object.entries(result.parent_matches)
        .filter(([, value]) => value)
        .map(([key]) => key.replaceAll("_", " "))
        .join(", ");
      setNotice(`Project-local village active. Matching parent: ${matched}.`);
      setConfirmation("");
      onAuthorized();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Project-local village authorization failed"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section
      data-testid="project-local-village-authorization"
      className="space-y-3 rounded-xl border border-cyan-200 bg-cyan-50 p-3"
    >
      <div>
        <h3 className="font-semibold text-cyan-950">
          Authorize project-local village
        </h3>
        <p className="text-xs text-cyan-800">
          One project administrator may authorize this unmapped NWDP village
          when at least one parent matches. Global LGD and PIN links remain unchanged.
          Android exposure is not enabled by this action.
        </p>
      </div>
      <div className="rounded-lg bg-white p-2 text-sm">
        <strong>{candidate.source_village_name || "Unnamed NWDP village"}</strong>
        <div className="text-xs text-slate-600">
          {candidate.source_block_name || "unknown block"} ·{" "}
          {candidate.source_district_name || "unknown district"} ·{" "}
          {candidate.source_state_name || "unknown state"}
        </div>
      </div>
      <label className="block text-sm">
        Authorization reason
        <textarea
          aria-label="Project-local village authorization reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          className="mt-1 w-full rounded-lg border p-2"
        />
      </label>
      <label className="block text-sm">
        Type AUTHORIZE PROJECT LOCAL VILLAGE
        <input
          aria-label="Project-local village confirmation"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          className="mt-1 w-full rounded-lg border p-2"
        />
      </label>
      <button
        type="button"
        disabled={
          loading ||
          reason.trim().length < 8 ||
          confirmation !== "AUTHORIZE PROJECT LOCAL VILLAGE"
        }
        onClick={() => void authorize()}
        className="rounded-lg bg-cyan-800 px-3 py-2 text-sm font-semibold text-white disabled:bg-slate-300"
      >
        Authorize for this project only
      </button>
      {notice && <p className="text-sm font-medium text-emerald-700">{notice}</p>}
      {error && <p className="text-sm font-medium text-rose-700">{error}</p>}
    </section>
  );
}
