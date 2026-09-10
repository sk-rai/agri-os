"use client";

import { useEffect, useMemo, useState } from "react";
import {
  geographyApi,
  type GeographyDistrict,
  type GeographyState,
  type GeographyVillageDetails,
  type GeographyVillageSearchResult,
} from "@/lib/api";

interface SelectedVillage {
  lgdCode: string;
  name?: string;
  blockName?: string;
  districtName?: string;
  stateName?: string;
}

interface GeographyVillagePickerProps {
  value: string[];
  onChange: (codes: string[]) => void;
  disabled?: boolean;
}

export function GeographyVillagePicker({
  value,
  onChange,
  disabled = false,
}: GeographyVillagePickerProps) {
  const [states, setStates] = useState<GeographyState[]>([]);
  const [districts, setDistricts] = useState<GeographyDistrict[]>([]);
  const [searchMode, setSearchMode] = useState<
    "district" | "india"
  >("district");
  const [stateId, setStateId] = useState("");
  const [districtId, setDistrictId] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeographyVillageSearchResult[]>([]);
  const [knownVillages, setKnownVillages] = useState<
    Record<string, SelectedVillage>
  >({});
  const [loadingStates, setLoadingStates] = useState(true);
  const [loadingDistricts, setLoadingDistricts] = useState(false);
  const [searching, setSearching] = useState(false);
  const [hydratingCodes, setHydratingCodes] = useState(false);
  const [error, setError] = useState("");

  const selectedCodes = useMemo(() => new Set(value), [value]);

  useEffect(() => {
    const missingCodes = value.filter((code) => !knownVillages[code]);
    if (!missingCodes.length) {
      setHydratingCodes(false);
      return;
    }

    let active = true;
    setHydratingCodes(true);
    geographyApi
      .resolveVillagesByLgdCodes(missingCodes)
      .then((rows: GeographyVillageDetails[]) => {
        if (!active || !rows.length) return;
        setKnownVillages((current) => {
          const hydrated = { ...current };
          rows.forEach((village) => {
            hydrated[village.lgd_code] = {
              lgdCode: village.lgd_code,
              name: village.canonical_name,
              blockName: village.block_name,
              districtName: village.district_name,
              stateName: village.state_name,
            };
          });
          return hydrated;
        });
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to resolve saved villages",
          );
        }
      })
      .finally(() => {
        if (active) setHydratingCodes(false);
      });

    return () => {
      active = false;
    };
  }, [knownVillages, value]);

  useEffect(() => {
    let active = true;
    setLoadingStates(true);
    geographyApi
      .listStates()
      .then((rows) => {
        if (active) setStates(rows);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error ? err.message : "Failed to load states",
          );
        }
      })
      .finally(() => {
        if (active) setLoadingStates(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setDistrictId("");
    setDistricts([]);
    setResults([]);
    setQuery("");
    if (!stateId) return;

    let active = true;
    setLoadingDistricts(true);
    setError("");
    geographyApi
      .listDistricts(stateId)
      .then((rows) => {
        if (active) setDistricts(rows);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error ? err.message : "Failed to load districts",
          );
        }
      })
      .finally(() => {
        if (active) setLoadingDistricts(false);
      });
    return () => {
      active = false;
    };
  }, [stateId]);

  useEffect(() => {
    const trimmedQuery = query.trim();
    if (
      trimmedQuery.length < 2 ||
      (searchMode === "district" && !districtId)
    ) {
      setResults([]);
      setSearching(false);
      return;
    }

    let active = true;
    const timer = window.setTimeout(() => {
      setSearching(true);
      setError("");
      geographyApi
        .searchVillages(
          trimmedQuery,
          searchMode === "district" ? districtId : undefined,
        )
        .then((rows) => {
          if (active) setResults(rows);
        })
        .catch((err: unknown) => {
          if (active) {
            setResults([]);
            setError(
              err instanceof Error ? err.message : "Village search failed",
            );
          }
        })
        .finally(() => {
          if (active) setSearching(false);
        });
    }, 300);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [districtId, query, searchMode]);

  const selectVillage = (village: GeographyVillageSearchResult) => {
    setKnownVillages((current) => ({
      ...current,
      [village.lgd_code]: {
        lgdCode: village.lgd_code,
        name: village.canonical_name,
        blockName: village.block_name,
        districtName: village.district_name,
        stateName: village.state_name,
      },
    }));
    if (!selectedCodes.has(village.lgd_code)) {
      onChange([...value, village.lgd_code]);
    }
  };

  const removeVillage = (lgdCode: string) => {
    onChange(value.filter((code) => code !== lgdCode));
  };

  return (
    <div className="mt-3">
      <div
        aria-label="Village search mode"
        className="flex flex-wrap gap-2"
      >
        <button
          type="button"
          aria-pressed={searchMode === "district"}
          disabled={disabled}
          onClick={() => {
            setSearchMode("district");
            setQuery("");
            setResults([]);
          }}
          className={`rounded border px-3 py-2 text-xs font-semibold ${
            searchMode === "district"
              ? "border-green-700 bg-green-700 text-white"
              : "border-gray-300 bg-white text-gray-700"
          }`}
        >
          Search by state and district
        </button>
        <button
          type="button"
          aria-pressed={searchMode === "india"}
          disabled={disabled}
          onClick={() => {
            setSearchMode("india");
            setQuery("");
            setResults([]);
          }}
          className={`rounded border px-3 py-2 text-xs font-semibold ${
            searchMode === "india"
              ? "border-green-700 bg-green-700 text-white"
              : "border-gray-300 bg-white text-gray-700"
          }`}
        >
          Search across India
        </button>
      </div>

      {searchMode === "district" ? (
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        <label className="block text-xs font-medium text-gray-700">
          State / Union Territory
          <select
            aria-label="State / Union Territory"
            value={stateId}
            disabled={disabled || loadingStates}
            onChange={(event) => setStateId(event.target.value)}
            className="mt-1 w-full rounded border bg-white px-3 py-2 text-sm"
          >
            <option value="">
              {loadingStates ? "Loading states…" : "Select state"}
            </option>
            {states.map((state) => (
              <option key={state.id} value={state.id}>
                {state.canonical_name} ({state.lgd_code})
              </option>
            ))}
          </select>
        </label>

        <label className="block text-xs font-medium text-gray-700">
          District
          <select
            aria-label="District"
            value={districtId}
            disabled={disabled || !stateId || loadingDistricts}
            onChange={(event) => {
              setDistrictId(event.target.value);
              setQuery("");
              setResults([]);
            }}
            className="mt-1 w-full rounded border bg-white px-3 py-2 text-sm"
          >
            <option value="">
              {loadingDistricts ? "Loading districts…" : "Select district"}
            </option>
            {districts.map((district) => (
              <option key={district.id} value={district.id}>
                {district.canonical_name} ({district.lgd_code})
              </option>
            ))}
          </select>
        </label>
      </div>
      ) : (
        <p className="mt-3 text-xs text-gray-600">
          Search all active canonical villages by name. Confirm the state,
          district, block, and LGD code before selecting.
        </p>
      )}

      <label className="mt-3 block text-xs font-medium text-gray-700">
        Search villages
        <input
          type="search"
          aria-label="Search villages"
          value={query}
          disabled={
            disabled ||
            (searchMode === "district" && !districtId)
          }
          onChange={(event) => setQuery(event.target.value)}
          placeholder={
            searchMode === "india"
              ? "Search village names across India"
              : districtId
                ? "Type at least 2 characters"
                : "Select a state and district first"
          }
          className="mt-1 w-full rounded border bg-white px-3 py-2 text-sm"
        />
      </label>

      {searching ? (
        <p className="mt-2 text-xs text-gray-500">Searching villages…</p>
      ) : null}

      {!searching &&
      query.trim().length >= 2 &&
      (searchMode === "india" || districtId) ? (
        <div
          aria-label="Village search results"
          className="mt-2 max-h-56 overflow-y-auto rounded border bg-white"
        >
          {results.length ? (
            results.map((village) => {
              const selected = selectedCodes.has(village.lgd_code);
              return (
                <button
                  key={village.id}
                  type="button"
                  disabled={disabled || selected}
                  onClick={() => selectVillage(village)}
                  className="flex w-full items-start justify-between gap-3 border-b px-3 py-2 text-left last:border-b-0 hover:bg-green-50 disabled:bg-gray-50"
                >
                  <span>
                    <span className="block text-sm font-medium text-gray-900">
                      {village.canonical_name}
                    </span>
                    <span className="block text-xs text-gray-500">
                      {village.state_name} / {village.district_name} /{" "}
                      {village.block_name}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-xs text-gray-600">
                    {selected ? "Selected" : `LGD ${village.lgd_code}`}
                  </span>
                </button>
              );
            })
          ) : (
            <p className="px-3 py-4 text-sm text-gray-500">
              No matching active villages found.
            </p>
          )}
        </div>
      ) : null}

      <div className="mt-4">
        <p className="text-xs font-medium text-gray-700">
          Selected villages ({value.length})
          {hydratingCodes ? (
            <span className="ml-2 font-normal text-gray-500">
              Resolving saved names…
            </span>
          ) : null}
        </p>
        {value.length ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {value.map((code) => {
              const village = knownVillages[code];
              return (
                <span
                  key={code}
                  className="inline-flex items-center gap-2 rounded-full border border-green-300 bg-white px-3 py-1 text-xs text-green-900"
                >
                  <span>
                    <span className="block font-medium">
                      {village?.name || "Unresolved village"} · LGD {code}
                    </span>
                    {village ? (
                      <span className="block text-[11px] text-gray-500">
                        {[village.stateName, village.districtName, village.blockName]
                          .filter(Boolean)
                          .join(" / ")}
                      </span>
                    ) : null}
                  </span>
                  <button
                    type="button"
                    aria-label={`Remove village LGD ${code}`}
                    disabled={disabled}
                    onClick={() => removeVillage(code)}
                    className="font-bold text-green-700 hover:text-red-600 disabled:opacity-50"
                  >
                    ×
                  </button>
                </span>
              );
            })}
          </div>
        ) : (
          <p className="mt-2 text-xs text-gray-500">
            No villages selected. Search above to add one or more villages.
          </p>
        )}
      </div>

      {error ? (
        <p role="alert" className="mt-2 text-xs text-red-600">
          {error}
        </p>
      ) : null}
    </div>
  );
}
