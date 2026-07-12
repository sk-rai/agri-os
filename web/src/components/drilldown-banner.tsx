import Link from "next/link";
import type { ReactNode } from "react";

type DrilldownBannerProps = {
  title: string;
  description: ReactNode;
  clearHref: string;
  className?: string;
  actions?: ReactNode;
};

export function DrilldownBanner({ title, description, clearHref, className = "", actions }: DrilldownBannerProps) {
  return (
    <div className={`rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900 ${className}`}>
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="font-semibold">{title}</p>
          <p className="mt-1">{description}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {actions}
          <Link href={clearHref} className="rounded bg-white/80 px-3 py-1 text-xs font-semibold text-blue-800 hover:bg-white">
            Clear drill-down
          </Link>
        </div>
      </div>
    </div>
  );
}
