"use client";

import { useEffect, useState } from "react";
import { conflictsApi, type Conflict } from "@/lib/api";
import { adminRoleLabel, hasAdminPermission, useAdminProfile } from "@/lib/admin-permissions";
import { getErrorMessage, isPermissionDenied, PermissionErrorCard } from "@/components/permission-error-card";

export default function ConflictsPage() {
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Conflict | null>(null);
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const { profile: adminProfile, loading: adminProfileLoading } = useAdminProfile();
  const canResolveConflicts = hasAdminPermission(adminProfile, "EDIT");

  const loadConflicts = () => {
    conflictsApi.list("PENDING_REVIEW").then(setConflicts).catch((e) => setError(e)).finally(() => setLoading(false));
  };

  useEffect(() => { loadConflicts(); }, []);

  const handleResolve = async (id: string, strategy: string) => {
    if (!canResolveConflicts) return;
    setError(null);
    setResolving(true);
    try {
      await conflictsApi.resolve(id, strategy, "Resolved via web admin");
      setSelected(null);
      loadConflicts();
    } catch (e) {
      setError(e);
    } finally {
      setResolving(false);
    }
  };

  const conflictTypeColor: Record<string, string> = {
    VERSION_MISMATCH: "bg-yellow-100 text-yellow-800",
    GEO_OVERLAP: "bg-red-100 text-red-800",
    WORKFLOW_INVALID: "bg-purple-100 text-purple-800",
    DEPENDENCY_MISSING: "bg-gray-100 text-gray-800",
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">
        Sync Conflicts ({conflicts.length} pending)
      </h1>

      {!adminProfileLoading && !canResolveConflicts ? (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-semibold">Conflict resolution is read-only for your role</p>
          <p className="mt-1">Role {adminRoleLabel(adminProfile)} can inspect sync conflicts, but cannot accept client/server payloads.</p>
        </div>
      ) : null}

      {isPermissionDenied(error) ? <PermissionErrorCard error={error} className="mb-4" /> : error ? <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{getErrorMessage(error)}</div> : null}

      {loading ? (
        <p className="text-gray-500">Loading...</p>
      ) : conflicts.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-4xl mb-2">✅</p>
          <p className="text-gray-500">No pending conflicts. All syncs are clean.</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {conflicts.map((c) => (
            <div
              key={c.id}
              className={`bg-white rounded-lg shadow p-4 cursor-pointer hover:ring-2 hover:ring-green-300 transition ${
                selected?.id === c.id ? "ring-2 ring-green-500" : ""
              }`}
              onClick={() => setSelected(c)}
            >
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${conflictTypeColor[c.conflict_type] || "bg-gray-100"}`}>
                      {c.conflict_type}
                    </span>
                    <span className="text-sm text-gray-500">{c.entity_type}</span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1 font-mono">
                    Event: {c.event_id.slice(0, 8)}... | Entity: {c.entity_id.slice(0, 8)}...
                  </p>
                </div>
                <p className="text-xs text-gray-400">
                  {new Date(c.created_at).toLocaleDateString()}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Resolution Panel */}
      {selected && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <h2 className="text-lg font-bold mb-4">Resolve Conflict</h2>

            <div className="grid grid-cols-2 gap-4 mb-6">
              <div>
                <h3 className="text-sm font-medium text-blue-700 mb-2">📱 Client (Mobile)</h3>
                <pre className="bg-blue-50 p-3 rounded text-xs overflow-auto max-h-40">
                  {JSON.stringify(selected.client_payload, null, 2)}
                </pre>
              </div>
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">🖥️ Server</h3>
                <pre className="bg-gray-50 p-3 rounded text-xs overflow-auto max-h-40">
                  {JSON.stringify(selected.server_payload, null, 2)}
                </pre>
              </div>
            </div>

            {!canResolveConflicts ? (
              <div className="mb-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Your role can inspect this conflict but cannot resolve it.</div>
            ) : null}

            <div className="flex gap-3">
              <button
                onClick={() => handleResolve(selected.id, "ACCEPT_CLIENT")}
                disabled={resolving || !canResolveConflicts}
                title={canResolveConflicts ? undefined : "Your role cannot resolve sync conflicts."}
                className="flex-1 bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                Accept Client
              </button>
              <button
                onClick={() => handleResolve(selected.id, "ACCEPT_SERVER")}
                disabled={resolving || !canResolveConflicts}
                title={canResolveConflicts ? undefined : "Your role cannot resolve sync conflicts."}
                className="flex-1 bg-gray-600 text-white py-2 rounded-lg hover:bg-gray-700 disabled:opacity-50"
              >
                Accept Server
              </button>
              <button
                onClick={() => setSelected(null)}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
