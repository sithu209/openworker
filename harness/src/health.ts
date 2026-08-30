import {
  ACP_RC5_CAPABILITIES,
  OPENWORKER_HARNESS_BRIDGE_VERSION,
  type HarnessBridgeHello,
} from "./protocol.js";

export type HarnessHealthStatus = "ready" | "degraded" | "unavailable";

export interface HarnessHealthReport extends HarnessBridgeHello {
  status: HarnessHealthStatus;
  detail?: string;
}

export const PINNED_UPSTREAM_COMMIT =
  "47f943859bef60e4160492346772ded9b24f765a" as const;
export const PINNED_DSH_VERSION = "0.1.0-rc.5" as const;
export const PINNED_ACP_VERSION = "0.1.0-rc.5" as const;

export function expectedHealth(
  status: HarnessHealthStatus = "degraded",
  detail = "H2 contract only; Harness runtime is not enabled",
): HarnessHealthReport {
  return {
    bridgeVersion: OPENWORKER_HARNESS_BRIDGE_VERSION,
    upstreamCommit: PINNED_UPSTREAM_COMMIT,
    dshVersion: PINNED_DSH_VERSION,
    acpVersion: PINNED_ACP_VERSION,
    capabilities: { ...ACP_RC5_CAPABILITIES },
    status,
    detail,
  };
}
