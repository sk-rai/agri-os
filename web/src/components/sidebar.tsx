"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = { href: string; label: string; icon: string };
type NavSection = { label: string; items: NavItem[] };

const navSections: NavSection[] = [
  {
    label: "Overview",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: "Chart" },
      { href: "/my-access", label: "My Access", icon: "Lock" },
    ],
  },
  {
    label: "Organization",
    items: [
      { href: "/tenants", label: "Tenants", icon: "Tenant" },
      { href: "/projects", label: "Projects", icon: "Project" },
      { href: "/users", label: "Tenant Users", icon: "Users" },
    ],
  },
  {
    label: "Configuration",
    items: [
      { href: "/workflows", label: "Workflows", icon: "Crop" },
      { href: "/crop-taxonomy", label: "Crop Setup", icon: "Tax" },
      { href: "/project-workflows", label: "Project Workflows", icon: "Flow" },
      { href: "/profile-forms", label: "Profile Forms", icon: "Form" },
      { href: "/inputs", label: "Inputs", icon: "Input" },
      { href: "/products", label: "Products & Brands", icon: "Box" },
      { href: "/project-inputs", label: "Project Inputs", icon: "Tune" },
    ],
  },
  {
    label: "Traceability",
    items: [
      { href: "/activity-usage", label: "Activity Usage", icon: "Trend" },
      { href: "/project-enrollments", label: "Project Enrollments", icon: "Enroll" },
      { href: "/field-events", label: "Field Events", icon: "Event" },
      { href: "/query-threads", label: "Query Inbox", icon: "Chat" },
      { href: "/lookup", label: "Lookup", icon: "Search" },
    ],
  },
  {
    label: "Operations",
    items: [
      { href: "/sync-health", label: "Sync Health", icon: "Pulse" },
      { href: "/conflicts", label: "Conflicts", icon: "Warn" },
    ],
  },
];

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex min-h-screen w-64 flex-col bg-gray-900 p-4 text-white">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-green-400">Agri-OS</h1>
        <p className="mt-1 text-xs text-gray-400">Admin Dashboard</p>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto pb-6">
        {navSections.map((section) => (
          <div key={section.label}>
            <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
              {section.label}
            </p>
            <div className="space-y-1">
              {section.items.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                      active
                        ? "bg-green-700 text-white"
                        : "text-gray-300 hover:bg-gray-800 hover:text-white"
                    }`}
                  >
                    <span className="w-10 shrink-0 rounded bg-gray-800 px-1.5 py-0.5 text-center text-[10px] font-semibold text-gray-400">
                      {item.icon}
                    </span>
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <button
        onClick={() => {
          localStorage.removeItem("agrios_token");
          localStorage.removeItem("agrios_tenant_id");
          window.location.href = "/login";
        }}
        className="mt-4 rounded-lg px-3 py-2 text-left text-xs text-gray-500 hover:bg-gray-800 hover:text-red-400"
      >
        Logout
      </button>
    </aside>
  );
}
