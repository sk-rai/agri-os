"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { projectsApi, type Project } from "@/lib/api";
import { adminRoleLabel, hasAdminPermission, useAdminProfile } from "@/lib/admin-permissions";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: "", start_date: "", end_date: "", crop_scope: "",
  });
  const [error, setError] = useState("");
  const { profile: adminProfile, loading: adminProfileLoading } = useAdminProfile();
  const canCreateProjects = hasAdminPermission(adminProfile, "PROJECT_EDIT") || hasAdminPermission(adminProfile, "EDIT");

  const loadProjects = () => {
    projectsApi.list().then(setProjects).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { loadProjects(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canCreateProjects) {
      setError("Your current role can view projects but cannot create project configuration.");
      return;
    }
    setError("");
    try {
      await projectsApi.create({
        name: formData.name,
        start_date: formData.start_date,
        end_date: formData.end_date,
        crop_scope: formData.crop_scope.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean),
        geography_scope: {},
      });
      setShowForm(false);
      setFormData({ name: "", start_date: "", end_date: "", crop_scope: "" });
      loadProjects();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    }
  };

  const statusColor: Record<string, string> = {
    PLANNED: "bg-blue-100 text-blue-700",
    ACTIVE: "bg-green-100 text-green-700",
    COMPLETED: "bg-gray-100 text-gray-700",
    ARCHIVED: "bg-gray-100 text-gray-500",
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
        <button
          disabled={!canCreateProjects}
          title={canCreateProjects ? undefined : "Your role cannot create projects."}
          onClick={() => setShowForm(!showForm)}
          className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 text-sm disabled:opacity-50"
        >
          + New Project
        </button>
      </div>

      {!adminProfileLoading && !canCreateProjects ? (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-semibold">Projects are read-only for your role</p>
          <p className="mt-1">Role {adminRoleLabel(adminProfile)} can browse project records and compliance, but cannot create project configuration.</p>
        </div>
      ) : null}

      {showForm && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Create Project</h2>
          {error && <p className="text-red-500 text-sm mb-3">{error}</p>}
          <form onSubmit={handleCreate} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input type="text" placeholder="Project Name" value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="px-3 py-2 border rounded-lg" required />
            <input type="text" placeholder="Crops (comma-separated: RICE,WHEAT)"
              value={formData.crop_scope}
              onChange={(e) => setFormData({ ...formData, crop_scope: e.target.value })}
              className="px-3 py-2 border rounded-lg" />
            <input type="date" value={formData.start_date}
              onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
              className="px-3 py-2 border rounded-lg" required />
            <input type="date" value={formData.end_date}
              onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
              className="px-3 py-2 border rounded-lg" required />
            <button type="submit" disabled={!canCreateProjects} title={canCreateProjects ? undefined : "Your role cannot create projects."} className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 md:col-span-2 disabled:opacity-50">
              Create Project
            </button>
          </form>
        </div>
      )}

      {loading ? (
        <p className="text-gray-500">Loading...</p>
      ) : (
        <div className="grid gap-4">
          {projects.map((p) => (
            <div key={p.id} className="bg-white rounded-lg shadow p-4">
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-semibold text-gray-900">{p.name}</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    {p.start_date} → {p.end_date}
                  </p>
                  {p.crop_scope.length > 0 && (
                    <div className="flex gap-1 mt-2">
                      {p.crop_scope.map((c) => (
                        <span key={c} className="px-2 py-0.5 bg-green-50 text-green-700 rounded text-xs">{c}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex flex-col items-end gap-2">
                  <span className={`px-2 py-1 rounded text-xs ${statusColor[p.status] || "bg-gray-100"}`}>
                    {p.status}
                  </span>
                  <Link href={`/project-compliance/${p.id}`} className="text-xs text-blue-600 hover:underline">Compliance</Link>
                </div>
              </div>
            </div>
          ))}
          {projects.length === 0 && (
            <p className="text-center text-gray-400 py-8">No projects yet. Create one to get started.</p>
          )}
        </div>
      )}
    </div>
  );
}
