"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: "📊" },
  { href: "/tenants", label: "Tenants", icon: "🏢" },
  { href: "/projects", label: "Projects", icon: "📋" },
  { href: "/conflicts", label: "Conflicts", icon: "⚠️" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-gray-900 text-white min-h-screen p-4">
      <div className="mb-8">
        <h1 className="text-xl font-bold text-green-400">🌾 Agri-OS</h1>
        <p className="text-xs text-gray-400 mt-1">Admin Dashboard</p>
      </div>
      <nav className="space-y-1">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
              pathname === item.href
                ? "bg-green-700 text-white"
                : "text-gray-300 hover:bg-gray-800 hover:text-white"
            }`}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
      <div className="absolute bottom-4 left-4">
        <button
          onClick={() => {
            localStorage.removeItem("agrios_token");
            localStorage.removeItem("agrios_tenant_id");
            window.location.href = "/login";
          }}
          className="text-xs text-gray-500 hover:text-red-400"
        >
          Logout
        </button>
      </div>
    </aside>
  );
}
