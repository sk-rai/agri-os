"use client";

import { useEffect, useMemo, useState } from "react";
import { inputCatalogApi, type AgriInputDto, type InputCategoryDto } from "@/lib/api";

export default function InputsPage() {
  const [categories, setCategories] = useState<InputCategoryDto[]>([]);
  const [inputs, setInputs] = useState<AgriInputDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState("");
  const [cropCode, setCropCode] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    inputCatalogApi
      .categories()
      .then((data) => setCategories(data.categories))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    setLoading(true);
    inputCatalogApi
      .inputs({ category: category || undefined, cropCode: cropCode || undefined, q: query || undefined })
      .then((data) => setInputs(data.inputs))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [category, cropCode, query]);

  const cropOptions = useMemo(() => {
    const all = new Set<string>();
    inputs.forEach((item) => item.applicable_crops.forEach((crop) => all.add(crop)));
    ["RICE", "SUGARCANE", "WHEAT", "POTATO"].forEach((crop) => all.add(crop));
    return Array.from(all).sort();
  }, [inputs]);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    inputs.forEach((item) => {
      if (item.category_code) counts[item.category_code] = (counts[item.category_code] || 0) + 1;
    });
    return counts;
  }, [inputs]);

  if (error) return <div className="text-red-500">Error: {error}</div>;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Input Catalog</h1>
        <p className="mt-1 text-sm text-gray-500">
          Read-only catalog of canonical seeds, fertilizers, crop protection, labor, machinery, and irrigation inputs.
        </p>
      </div>

      <div className="mb-6 grid gap-3 rounded-lg bg-white p-4 shadow md:grid-cols-[1fr_220px_180px]">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search code, name, or composition"
          className="rounded-lg border px-3 py-2 text-sm"
        />
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">
          <option value="">All categories</option>
          {categories.map((cat) => (
            <option key={cat.code} value={cat.code}>{cat.canonical_name}</option>
          ))}
        </select>
        <select value={cropCode} onChange={(e) => setCropCode(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">
          <option value="">All crops</option>
          {cropOptions.map((crop) => (
            <option key={crop} value={crop}>{crop}</option>
          ))}
        </select>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        {categories.slice(0, 14).map((cat) => (
          <button
            key={cat.code}
            onClick={() => setCategory(category === cat.code ? "" : cat.code)}
            className={`rounded-lg border p-3 text-left text-sm shadow-sm ${
              category === cat.code ? "border-green-500 bg-green-50" : "border-transparent bg-white hover:border-green-200"
            }`}
          >
            <p className="font-medium text-gray-900">{cat.canonical_name}</p>
            <p className="mt-1 text-xs text-gray-400">{categoryCounts[cat.code] || 0} shown</p>
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-gray-500">Loading inputs...</p>
      ) : (
        <div className="overflow-hidden rounded-lg bg-white shadow">
          <table className="w-full text-sm">
            <thead className="border-b bg-gray-50 text-xs text-gray-500">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Code</th>
                <th className="px-4 py-3 text-left font-medium">Name</th>
                <th className="px-4 py-3 text-left font-medium">Category</th>
                <th className="px-4 py-3 text-left font-medium">Composition</th>
                <th className="px-4 py-3 text-left font-medium">Unit</th>
                <th className="px-4 py-3 text-left font-medium">Crops</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {inputs.map((item) => (
                <tr key={item.code} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">{item.code}</td>
                  <td className="px-4 py-3">
                    <p className="font-medium text-gray-900">{item.canonical_name}</p>
                    {item.brand_name ? <p className="text-xs text-gray-400">Brand: {item.brand_name}</p> : null}
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">
                      {item.category_code || "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{item.composition || "—"}</td>
                  <td className="px-4 py-3 text-gray-600">{item.unit}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {item.applicable_crops.length > 0 ? item.applicable_crops.map((crop) => (
                        <span key={crop} className="rounded bg-green-50 px-2 py-0.5 text-xs text-green-700">{crop}</span>
                      )) : <span className="text-gray-400">—</span>}
                    </div>
                  </td>
                </tr>
              ))}
              {inputs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-gray-400">No inputs match this filter.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
