"use client";

import { useState } from "react";

type CopyLinkButtonProps = {
  href: string;
  label?: string;
  copiedLabel?: string;
  className?: string;
};

export function CopyLinkButton({ href, label = "Copy link", copiedLabel = "Copied", className = "" }: CopyLinkButtonProps) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    const target = typeof window === "undefined" ? href : new URL(href, window.location.origin).toString();
    await navigator.clipboard.writeText(target);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <button type="button" onClick={copy} className={className}>
      {copied ? copiedLabel : label}
    </button>
  );
}
