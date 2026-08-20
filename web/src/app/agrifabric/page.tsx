import type { Metadata } from "next";
import { AgriFabricLandingClient } from "./AgriFabricLandingClient";

export const metadata: Metadata = {
  title: "AgriFabric | Field evidence fabric for agriculture programs",
  description:
    "Offline-first field evidence, project operations, advisories, sync resilience, geography, and governance for agriculture programs.",
};

export default function AgriFabricLandingPage() {
  return <AgriFabricLandingClient />;
}
