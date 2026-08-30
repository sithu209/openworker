import assert from "node:assert/strict";
import test from "node:test";

import {
  ACP_RC5_CAPABILITIES,
  OPENWORKER_HARNESS_BRIDGE_VERSION,
  validateHello,
} from "../lib/protocol.js";
import {
  PINNED_ACP_VERSION,
  PINNED_DSH_VERSION,
  PINNED_UPSTREAM_COMMIT,
  expectedHealth,
} from "../lib/health.js";

test("H2 pins the reviewed DeepSeek Harness rc.5 upstream", () => {
  assert.equal(PINNED_UPSTREAM_COMMIT, "47f943859bef60e4160492346772ded9b24f765a");
  assert.equal(PINNED_DSH_VERSION, "0.1.0-rc.5");
  assert.equal(PINNED_ACP_VERSION, "0.1.0-rc.5");
});

test("ACP capabilities are explicit and conservative", () => {
  assert.equal(ACP_RC5_CAPABILITIES.transport, "acp-stdio");
  assert.equal(ACP_RC5_CAPABILITIES.freshSessions, true);
  assert.equal(ACP_RC5_CAPABILITIES.prompt, true);
  assert.equal(ACP_RC5_CAPABILITIES.cancel, true);
  assert.equal(ACP_RC5_CAPABILITIES.oneShotPermission, true);
  assert.equal(ACP_RC5_CAPABILITIES.committedAssistantText, true);

  for (const unsupported of [
    "resume",
    "replay",
    "liveReasoning",
    "liveToolEvents",
    "plans",
    "perSessionClose",
  ]) {
    assert.equal(ACP_RC5_CAPABILITIES[unsupported], false, unsupported);
  }
});

test("H2 health is degraded until a real Harness runtime is enabled", () => {
  const health = expectedHealth();
  assert.equal(health.status, "degraded");
  assert.equal(health.bridgeVersion, OPENWORKER_HARNESS_BRIDGE_VERSION);
  validateHello(health);
});

test("hello validation rejects protocol drift", () => {
  const health = expectedHealth();
  assert.throws(
    () => validateHello({ ...health, bridgeVersion: 2 }),
    /unsupported bridge version/,
  );
  assert.throws(
    () => validateHello({ ...health, upstreamCommit: "short" }),
    /40-character git SHA/,
  );
});
