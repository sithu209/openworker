export const OPENWORKER_HARNESS_BRIDGE_VERSION = 1 as const;

export type HarnessTransport = "acp-stdio";

export interface HarnessTransportCapabilities {
  transport: HarnessTransport;
  freshSessions: boolean;
  prompt: boolean;
  cancel: boolean;
  oneShotPermission: boolean;
  committedAssistantText: boolean;
  resume: boolean;
  replay: boolean;
  liveReasoning: boolean;
  liveToolEvents: boolean;
  plans: boolean;
  perSessionClose: boolean;
}

export const ACP_RC5_CAPABILITIES: Readonly<HarnessTransportCapabilities> =
  Object.freeze({
    transport: "acp-stdio",
    freshSessions: true,
    prompt: true,
    cancel: true,
    oneShotPermission: true,
    committedAssistantText: true,
    resume: false,
    replay: false,
    liveReasoning: false,
    liveToolEvents: false,
    plans: false,
    perSessionClose: false,
  });

export interface HarnessBridgeHello {
  bridgeVersion: typeof OPENWORKER_HARNESS_BRIDGE_VERSION;
  upstreamCommit: string;
  dshVersion: string;
  acpVersion: string;
  capabilities: HarnessTransportCapabilities;
}

export function validateHello(value: HarnessBridgeHello): void {
  if (value.bridgeVersion !== OPENWORKER_HARNESS_BRIDGE_VERSION) {
    throw new Error(`unsupported bridge version: ${value.bridgeVersion}`);
  }
  if (!/^[0-9a-f]{40}$/i.test(value.upstreamCommit)) {
    throw new Error("upstreamCommit must be a full 40-character git SHA");
  }
  if (value.capabilities.transport !== "acp-stdio") {
    throw new Error(`unsupported harness transport: ${value.capabilities.transport}`);
  }
}
