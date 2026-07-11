"use client";

import { useEffect, useState } from "react";
import { authApi, type AdminProfileResponse } from "@/lib/api";

export type AdminPermission = "VIEW" | "EDIT" | "PUBLISH" | "PROJECT_EDIT" | "MANAGE_USERS" | string;

export function hasAdminPermission(profile: AdminProfileResponse | null, permission: AdminPermission): boolean {
  return profile?.permissions.includes(permission) ?? false;
}

export function adminRoleLabel(profile: AdminProfileResponse | null): string {
  return (profile?.role || "UNASSIGNED").replaceAll("_", " ");
}

export function useAdminProfile() {
  const [profile, setProfile] = useState<AdminProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    authApi.me()
      .then((payload) => {
        if (!active) return;
        setProfile(payload);
        setError(null);
      })
      .catch((err) => {
        if (!active) return;
        setProfile(null);
        setError(err instanceof Error ? err.message : "Failed to load admin profile");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  return { profile, loading, error };
}
