"use client";

import { useEffect, useState } from "react";
import { dashboardApi, type Dashboard } from "@/lib/api";

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    dashboardApi
      .getOperational()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-500">Loading dashboard...</div>;
  if (error) return <div className="text-red-500">Error: {error}</div>;
  if (!data) return null;

  const { sync_health } = data;

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">
        Operational Dashboard
      </h1>

      {/* Sync Health Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Events Processed"
          value={sync_health.total_events_processed}
          color="blue"
        />
        <StatCard
          label="Committed"
          value={sync_health.committed}
          color="green"
        />
        <StatCard
          label="Conflicts Pending"
          value={sync_health.conflicts_pending}
          color="yellow"
        />
        <StatCard
          label="Failed"
          value={sync_health.failed}
          color="red"
        />
      </div>

      {/* Audit Chain */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Audit Chain</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-500">Chain Length</p>
            <p className="text-2xl font-bold">{sync_health.audit_chain_length}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Integrity</p>
            <p className={`text-2xl font-bold ${sync_health.audit_chain_intact ? "text-green-600" : "text-red-600"}`}>
              {sync_health.audit_chain_intact ? "✅ Intact" : "❌ Broken"}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Last Sync</p>
            <p className="text-sm font-mono">
              {sync_health.last_sync_at
                ? new Date(sync_health.last_sync_at).toLocaleString()
                : "No syncs yet"}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Conflicts Resolved</p>
            <p className="text-2xl font-bold text-green-600">
              {sync_health.conflicts_resolved}
            </p>
          </div>
        </div>
      </div>

      <p className="text-xs text-gray-400">
        Generated: {new Date(data.generated_at).toLocaleString()} | Tenant: {data.tenant_id}
      </p>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-50 border-blue-200 text-blue-700",
    green: "bg-green-50 border-green-200 text-green-700",
    yellow: "bg-yellow-50 border-yellow-200 text-yellow-700",
    red: "bg-red-50 border-red-200 text-red-700",
  };

  return (
    <div className={`rounded-lg border p-4 ${colorMap[color]}`}>
      <p className="text-sm opacity-75">{label}</p>
      <p className="text-3xl font-bold mt-1">{value}</p>
    </div>
  );
}
