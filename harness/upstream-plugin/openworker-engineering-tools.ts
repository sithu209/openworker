import type { Context } from '@deepseek-ai/cordis'
import type { JsonValue, ToolDefinition, ToolExecution } from '@deepseek-ai/dsh-tools'

export const name = 'openworker-engineering-tools'
export const inject = ['tools']

type OsAnnotations = {
  canonical_tool_id: string
  side_effect?: string
  requires_job_scope?: boolean
  cost_class?: string
}

type OsMcpTool = {
  name: string
  description?: string
  inputSchema: Record<string, unknown>
  annotations: OsAnnotations
}

type Config = {
  engineeringOsBaseUrl?: string
  engineeringOsToken?: string
  contextIngressUrl?: string
  contextIngressToken?: string
  projectId?: string
  jobId?: string
  componentId?: string
  allowPublish?: boolean
}

const trimBase = (value: string) => value.trim().replace(/\/+$/, '')
const consequential = (sideEffect: string | undefined) =>
  !['read', 'compute'].includes(String(sideEffect ?? '').trim().toLowerCase())

function required(value: string | undefined, label: string): string {
  const resolved = String(value ?? '').trim()
  if (!resolved) throw new Error(`openworker engineering tools: ${label} is required`)
  return resolved
}

function resolveConfig(config: Config) {
  return {
    engineeringOsBaseUrl: trimBase(
      required(
        config.engineeringOsBaseUrl ?? process.env.OPENWORKER_ENGINEERING_OS_BASE_URL,
        'engineeringOsBaseUrl',
      ),
    ),
    engineeringOsToken: String(
      config.engineeringOsToken ?? process.env.OPENWORKER_ENGINEERING_OS_TOKEN ?? '',
    ).trim(),
    contextIngressUrl: trimBase(
      required(
        config.contextIngressUrl ?? process.env.OPENWORKER_HARNESS_CONTEXT_URL,
        'contextIngressUrl',
      ),
    ),
    contextIngressToken: required(
      config.contextIngressToken ?? process.env.OPENWORKER_HARNESS_CONTEXT_TOKEN,
      'contextIngressToken',
    ),
    projectId: String(config.projectId ?? process.env.OPENWORKER_ENGINEERING_PROJECT_ID ?? '').trim(),
    jobId: String(config.jobId ?? process.env.OPENWORKER_ENGINEERING_JOB_ID ?? '').trim(),
    componentId: String(
      config.componentId ?? process.env.OPENWORKER_ENGINEERING_COMPONENT_ID ?? '',
    ).trim(),
    allowPublish:
      config.allowPublish ?? process.env.OPENWORKER_ENGINEERING_ALLOW_PUBLISH === '1',
  }
}

async function jsonRequest(
  url: string,
  init: RequestInit,
  label: string,
): Promise<Record<string, unknown>> {
  const response = await fetch(url, init)
  const text = await response.text()
  let payload: unknown
  try {
    payload = text ? JSON.parse(text) : {}
  } catch {
    throw new Error(`${label}: non-JSON response (${response.status})`)
  }
  if (!response.ok) {
    throw new Error(`${label}: HTTP ${response.status}: ${JSON.stringify(payload)}`)
  }
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
    throw new Error(`${label}: response must be a JSON object`)
  }
  return payload as Record<string, unknown>
}

function osHeaders(token: string): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'Content-Type': 'application/json',
  }
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

async function discover(baseUrl: string, token: string): Promise<OsMcpTool[]> {
  const payload = await jsonRequest(
    `${baseUrl}/api/v1/ai/tools/mcp`,
    { headers: osHeaders(token) },
    'Engineering-OS tool discovery',
  )
  if (!Array.isArray(payload.tools)) {
    throw new Error('Engineering-OS tool discovery: tools must be an array')
  }
  const seenNames = new Set<string>()
  const seenCanonical = new Set<string>()
  return payload.tools.map((raw, index) => {
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
      throw new Error(`Engineering-OS tool discovery: tool[${index}] must be an object`)
    }
    const value = raw as Record<string, unknown>
    const annotations = value.annotations
    const name = typeof value.name === 'string' ? value.name.trim() : ''
    if (!name) throw new Error(`Engineering-OS tool discovery: tool[${index}] has no name`)
    if (typeof value.inputSchema !== 'object' || value.inputSchema === null || Array.isArray(value.inputSchema)) {
      throw new Error(`${name}: inputSchema must be an object`)
    }
    if (typeof annotations !== 'object' || annotations === null || Array.isArray(annotations)) {
      throw new Error(`${name}: annotations are required`)
    }
    const ann = annotations as Record<string, unknown>
    const canonical =
      typeof ann.canonical_tool_id === 'string' ? ann.canonical_tool_id.trim() : ''
    if (!canonical) throw new Error(`${name}: canonical_tool_id is required`)
    if (seenNames.has(name)) throw new Error(`duplicate Engineering-OS tool name: ${name}`)
    if (seenCanonical.has(canonical)) {
      throw new Error(`duplicate Engineering-OS canonical tool id: ${canonical}`)
    }
    seenNames.add(name)
    seenCanonical.add(canonical)
    return {
      name,
      description: typeof value.description === 'string' ? value.description : '',
      inputSchema: value.inputSchema as Record<string, unknown>,
      annotations: {
        canonical_tool_id: canonical,
        side_effect: typeof ann.side_effect === 'string' ? ann.side_effect : '',
        requires_job_scope: Boolean(ann.requires_job_scope),
        cost_class: typeof ann.cost_class === 'string' ? ann.cost_class : '',
      },
    }
  })
}

async function registerContext(
  ingressUrl: string,
  token: string,
  exec: Readonly<ToolExecution>,
): Promise<void> {
  await jsonRequest(
    `${ingressUrl}/v1/harness/tool-context`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ callId: exec.callId, name: exec.name, arguments: exec.arguments }),
      signal: exec.signal,
    },
    'OpenWorker tool-context registration',
  )
}

async function discardContext(ingressUrl: string, token: string, callId: string): Promise<void> {
  try {
    await fetch(`${ingressUrl}/v1/harness/tool-context`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ callId }),
    })
  } catch {
    // Best-effort cleanup only. OpenWorker also treats duplicate/stale call ids as fail closed.
  }
}

export async function apply(ctx: Context, config: Config = {}) {
  const resolved = resolveConfig(config)
  const tools = await discover(resolved.engineeringOsBaseUrl, resolved.engineeringOsToken)
  const byName = new Map(tools.map((tool) => [tool.name, tool] as const))
  const registeredForApproval = new Set<string>()

  for (const tool of tools) {
    const definition: ToolDefinition = {
      name: tool.name,
      description: tool.description ?? '',
      parameters: tool.inputSchema,
      output: {
        // Engineering-OS ToolResult is an extensible JSON object. Keep the canonical
        // value intact; OpenWorker/OS own the field contract.
        schema: {},
        render: (_args: unknown, value: JsonValue) => [
          { type: 'text', text: JSON.stringify(value) },
        ],
      },
      async execute(args: unknown, exec) {
        if (tool.annotations.requires_job_scope && (!resolved.projectId || !resolved.jobId)) {
          throw new Error(`${tool.annotations.canonical_tool_id} requires projectId and jobId`)
        }
        const body: Record<string, unknown> = {
          project_id: resolved.projectId,
          job_id: resolved.jobId,
          arguments: args,
        }
        if (resolved.componentId) body.component_id = resolved.componentId
        if (resolved.allowPublish) body.allow_publish = true
        const canonical = encodeURIComponent(tool.annotations.canonical_tool_id)
        return jsonRequest(
          `${resolved.engineeringOsBaseUrl}/api/v1/ai/tools/${canonical}/invoke`,
          {
            method: 'POST',
            headers: osHeaders(resolved.engineeringOsToken),
            body: JSON.stringify(body),
            signal: exec.signal,
          },
          `${tool.annotations.canonical_tool_id} invocation`,
        )
      },
    }
    ctx.tools.register(definition)
  }

  ctx.on('tools/pre-execute', async (exec, next) => {
    const tool = byName.get(exec.name)
    if (!tool) return next()
    if (!consequential(tool.annotations.side_effect)) return next()

    // ACP approval only carries callId. Register the minimum raw call facts with
    // OpenWorker first; OpenWorker independently resolves trusted OS metadata.
    await registerContext(
      resolved.contextIngressUrl,
      resolved.contextIngressToken,
      exec,
    )
    registeredForApproval.add(String(exec.callId))
    return {
      kind: 'ask' as const,
      reason: `OpenWorker approval required for ${tool.annotations.canonical_tool_id}`,
    }
  })

  ctx.on('tools/result', (exec) => {
    const callId = String(exec.callId)
    if (!registeredForApproval.delete(callId)) return
    void discardContext(resolved.contextIngressUrl, resolved.contextIngressToken, callId)
  })
}
