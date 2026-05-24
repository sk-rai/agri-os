"use client";

import { useEffect, useState } from "react";
import { tenantsApi, type Tenant } from "@/lib/api";

export default function TenantsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ id: "", name: "", type: "ENTERPRISE" });
  const [error, setError] = useState("");

  const loadTenants = () => {
    tenantsApi.list().then(setTenants).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { loadTenants(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await tenantsApi.create(formData);
      setShowForm(false);
      setFormData({ id: "", name: "", type: "ENTERPRISE" });
      loadTenants();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create tenant");
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Tenants</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 text-sm"
        >
          + New Tenant
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Register New Tenant</h2>
          {error && <p className="text-red-500 text-sm mb-3">{error}</p>}
          <form onSubmit={handleCreate} className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <input
              type="text"
              placeholder="Tenant ID (e.g., iffco-up)"
              value={formData.id}
              onChange={(e) => setFormData({ ...formData, id: e.target.value })}
              pattern="^[a-z0-9-]+$"
              className="px-3 py-2 border rounded-lg"
              required
            />
            <input
              type="text"
              placeholder="Organization Name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="px-3 py-2 border rounded-lg"
              required
            />
            <select
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
              className="px-3 py-2 border rounded-lg"
            >
              <option value="ENTERPRISE">Enterprise</option>
              <option value="FPO">FPO</option>
              <option value="INSURER">Insurer</option>
              <option value="GOVERNMENT">Government</option>
            </select>
            <button type="submit" className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700">
              Create
            </button>
          </form>
        </div>
      )}

      {loading ? (
        <p className="text-gray-500">Loading...</p>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">ID</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Type</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {tenants.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs">{t.id}</td>
                  <td className="px-4 py-3 font-medium">{t.name}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs">{t.type}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-xs ${t.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {t.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                </tr>
              ))}
              {tenants.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-400">No tenants yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
