#!/usr/bin/env bun
// Cortex Team Channels MCP Server
// Keep in sync with cortex/models.py for shared types

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { MongoClient, type Collection, type Db } from "mongodb";

// ── Types (keep in sync with cortex/models.py) ──────────────

interface Message {
  _id: string;
  from: string;
  to: string;
  content: string;
  meta: Record<string, string>;
  status: "pending" | "claimed" | "delivered";
  created_at: string;
  delivered_at: string | null;
  claimed_by?: string;
  claimed_at?: string;
}

interface SessionDoc {
  _id: string;
  name: string;
  task?: string;
  team?: string;
  status: string;
  last_seen?: string | null;
  channel_status?: string;
  [key: string]: unknown;
}

// ── Config ───────────────────────────────────────────────────

const SESSION_NAME = process.env.CORTEX_SESSION_NAME;
const SESSION_ID = process.env.CORTEX_SESSION_ID;
const MONGODB_URI = process.env.CORTEX_MONGODB_URI;

const POLL_INTERVAL_MS = 1500;
const HEARTBEAT_INTERVAL_MS = 30_000;
const MAX_CONTENT_SIZE = 10_240;
const STALE_THRESHOLD_MS = 5 * 60 * 1000;
const META_KEY_RE = /^[a-zA-Z0-9_]+$/;

if (!process.env.TMUX) {
  process.stderr.write(
    "[cortex-team] Not running inside tmux — exiting (Cortex sessions are tmux-only)\n"
  );
  process.exit(0);
}

if (!SESSION_NAME || !SESSION_ID || !MONGODB_URI) {
  process.stderr.write(
    "[cortex-team] FATAL: CORTEX_SESSION_NAME, CORTEX_SESSION_ID, and CORTEX_MONGODB_URI are required\n"
  );
  process.exit(1);
}

// ── Logging ──────────────────────────────────────────────────

import { appendFileSync, mkdirSync, writeFileSync, unlinkSync } from "fs";
import { join } from "path";
import { createServer, type AddressInfo } from "http";

const LOG_DIR = join(process.env.HOME || "/tmp", ".cortex", "logs");
try { mkdirSync(LOG_DIR, { recursive: true }); } catch {}
const LOG_FILE = join(LOG_DIR, `channels-mcp-${SESSION_NAME || "unknown"}.log`);

function log(level: string, msg: string, extra?: Record<string, unknown>) {
  const entry = {
    ts: new Date().toISOString(),
    level,
    component: "channels-mcp",
    session: SESSION_NAME,
    msg,
    ...extra,
  };
  const line = JSON.stringify(entry) + "\n";
  process.stderr.write(line);
  try { appendFileSync(LOG_FILE, line); } catch {}
}

// Log all env vars on startup for debugging
log("info", "Environment", {
  CORTEX_SESSION_NAME: SESSION_NAME || "<missing>",
  CORTEX_SESSION_ID: SESSION_ID || "<missing>",
  CORTEX_MONGODB_URI: MONGODB_URI ? "<set>" : "<missing>",
  NODE_ENV: process.env.NODE_ENV || "<unset>",
  cwd: process.cwd(),
  pid: process.pid,
});

// ── Channel Transport ────────────────────────────────────────

class ChannelTransport {
  constructor(private server: Server) {}

  async deliver(
    content: string,
    meta: Record<string, string>
  ): Promise<void> {
    const cleanMeta: Record<string, string> = {};
    for (const [k, v] of Object.entries(meta)) {
      if (META_KEY_RE.test(k)) {
        cleanMeta[k] = String(v);
      }
    }
    await this.server.notification({
      method: "notifications/claude/channel",
      params: { content, meta: cleanMeta },
    });
  }
}

// ── MongoDB ──────────────────────────────────────────────────

async function connectMongo(uri: string, retries = 3): Promise<Db> {
  let lastErr: Error | undefined;
  for (let i = 0; i < retries; i++) {
    try {
      const client = new MongoClient(uri);
      await client.connect();
      const db = client.db();
      await db.command({ ping: 1 });
      log("info", "MongoDB connected", { uri: uri.replace(/\/\/.*@/, "//<redacted>@") });
      return db;
    } catch (err) {
      lastErr = err as Error;
      log("warn", `MongoDB connect attempt ${i + 1}/${retries} failed`, {
        error: lastErr.message,
      });
      await new Promise((r) => setTimeout(r, 500 * (i + 1)));
    }
  }
  log("error", "MongoDB connection failed after retries");
  process.exit(1);
}

async function ensureIndexes(messages: Collection<Message>): Promise<void> {
  await messages.createIndex(
    { to: 1, status: 1, created_at: 1 },
    { name: "poll_query" }
  );
  await messages.createIndex(
    { created_at: 1 },
    { name: "ttl_cleanup", expireAfterSeconds: 7 * 24 * 60 * 60 }
  );
  log("info", "Indexes ensured on messages collection");
}

// ── ID generation ────────────────────────────────────────────

function newMsgId(): string {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  return "msg_" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

// ── Main ─────────────────────────────────────────────────────

const db = await connectMongo(MONGODB_URI!);
const messages = db.collection<Message>("messages");
const sessions = db.collection<SessionDoc>("session_registry");

await ensureIndexes(messages);

const deliveredSet = new Set<string>();

const SESSION_ROLE = process.env.CORTEX_SESSION_ROLE || "worker";

const BASE_INSTRUCTIONS = `Messages from other sessions arrive AUTOMATICALLY as <channel source="cortex-team" from="..." type="..." ...> notifications. You do NOT need to poll for them — they are pushed into your context between turns.

Use send_message to communicate with other sessions or the human operator.
Use get_status to see who's active and what they're working on.
Use get_messages ONLY to recover messages you might have missed (e.g. after context compaction). Do NOT use it to wait for replies — replies arrive as channel notifications automatically.

IMPORTANT — Immediate reply on new topics:
When you receive a channel message about a NEW topic (not a continuation of something already in your conversation), you MUST immediately reply to the sender via send_message BEFORE doing any work. A short acknowledgment is enough (e.g., "Got it, working on this now."). This confirms message delivery — the sender is waiting for your reply to verify you received it. Do not skip this step.

Messages are async. Don't wait for replies — continue your work.`;

const WORKER_INSTRUCTIONS = `${BASE_INSTRUCTIONS}

You are a WORKER session. There is a control session that coordinates all workers.

Message priority:
- Messages from the control session (name starts with "control-") are HIGH PRIORITY — these are instructions from the coordinator. Act on them immediately.
- Messages with meta.type="lifecycle" and meta.action="wrapup" mean you should wrap up: acknowledge, run /session-wrapup, update your status to completed, and /exit.
- Messages from other workers are PEER coordination — incorporate if relevant to your task, otherwise acknowledge and continue.

Reporting:
- If you have a parent session (CORTEX_PARENT_NAME is set), report to your parent via send_message.
- Otherwise, report progress, blockers, and completion to the control session via send_message.
- For urgent issues needing human attention, use send_message(to="human") — delivered via Slack.

Sub-workers:
- You can spawn sub-workers with \`cortex session spawn --name <name> --repo <repo> --prompt "..."\`
- Global limit: 15 active sessions. Use sub-workers for parallelizable subtasks.
- You are responsible for closing your sub-workers when done: \`cortex session close <name> --cascade\`

When you receive a message while working:
- Control message: pause current work, handle it, then resume
- Peer message relevant to your task: incorporate immediately
- Peer message unrelated: acknowledge and continue
- "stop", "wrong", "revert": pause and address immediately`;

const CONTROL_INSTRUCTIONS = `${BASE_INSTRUCTIONS}

You are the CONTROL session — the coordinator between the human and all worker sessions.

CRITICAL: You NEVER do implementation work. No reading code, no writing code, no running tests, no exploring codebases. When the human asks for any task, your FIRST action is to spawn a worker session for it.

Your only actions:
- Spawn workers: ALWAYS use \`cortex session spawn\` — never use the Agent tool or \`claude -p\`
- Send instructions: send_message(to="worker-name", content="...")
- Monitor: get_status, cortex session health, cortex session list --brief
- Close sessions: cortex session close <name> (--cascade to include children)
- Log to streams: cortex stream log/decide

Spawn + prompt delivery:
- When spawning with --prompt, the worker MUST reply within ~15 seconds confirming receipt.
- If no reply arrives, send the prompt again via send_message with: "Sending again as last message did not get any response — respond to this message immediately: <original prompt>"
- Only retry once. If still no reply after the second attempt, report the issue.

Message handling:
- Worker status updates: track progress, relay to human if noteworthy
- Worker questions: answer if you can, escalate to human via send_message(to="human") if not
- Worker blockers: help unblock or reassign work
- Human messages: translate into worker instructions and spawn/message workers`;

const INSTRUCTIONS = SESSION_ROLE === "control" ? CONTROL_INSTRUCTIONS : WORKER_INSTRUCTIONS;

const mcp = new Server(
  { name: "cortex-team", version: "1.0.0" },
  {
    capabilities: {
      experimental: { "claude/channel": {} },
      tools: {},
    },
    instructions: INSTRUCTIONS,
  }
);

const transport = new ChannelTransport(mcp);

// ── Tools ────────────────────────────────────────────────────

const TOOLS = [
  {
    name: "send_message",
    description:
      "Send a message to a specific team session or to 'human' for the human operator",
    inputSchema: {
      type: "object" as const,
      properties: {
        to: {
          type: "string",
          description: "Target session name, or 'human' for the human operator",
        },
        content: {
          type: "string",
          description: "Message body (max 10KB)",
        },
        meta: {
          type: "object",
          description:
            "Optional meta fields: type (notification|request|handoff|status_update), priority (normal|high), thread_id, reply_to",
          additionalProperties: { type: "string" },
        },
      },
      required: ["to", "content"],
    },
  },
  {
    name: "get_status",
    description: "Get status of all active sessions",
    inputSchema: {
      type: "object" as const,
      properties: {},
    },
  },
  {
    name: "get_messages",
    description: "Get recent messages for this session",
    inputSchema: {
      type: "object" as const,
      properties: {
        limit: {
          type: "number",
          description: "Max messages to return (default: 20)",
        },
        since: {
          type: "string",
          description:
            "ISO timestamp — return messages created after this time",
        },
      },
    },
  },
];

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  try {
    switch (name) {
      case "send_message":
        return await handleSendMessage(args as Record<string, unknown>);
      case "get_status":
        return await handleGetTeamStatus();
      case "get_messages":
        return await handleGetMessages(args as Record<string, unknown>);
      default:
        return {
          content: [{ type: "text", text: `Unknown tool: ${name}` }],
          isError: true,
        };
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    log("error", `Tool ${name} failed`, { error: msg });
    return {
      content: [{ type: "text", text: `Error: ${msg}` }],
      isError: true,
    };
  }
});

// ── Tool Handlers ────────────────────────────────────────────

async function handleSendMessage(args: Record<string, unknown>) {
  const to = String(args.to || "");
  const content = String(args.content || "");
  const meta = (args.meta as Record<string, string>) || {};

  if (!to) {
    return {
      content: [
        { type: "text", text: JSON.stringify({ success: false, error: "Missing 'to' field" }) },
      ],
    };
  }
  if (!content) {
    return {
      content: [
        { type: "text", text: JSON.stringify({ success: false, error: "Missing 'content' field" }) },
      ],
    };
  }
  if (content.length > MAX_CONTENT_SIZE) {
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({
            success: false,
            error: `Content exceeds ${MAX_CONTENT_SIZE} byte limit (${content.length} bytes)`,
          }),
        },
      ],
    };
  }

  // Validate recipient: "human" is reserved, otherwise check session registry
  if (to !== "human") {
    const target = await sessions.findOne({
      name: to,
      status: { $nin: ["completed", "closed"] },
    });
    if (!target) {
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              success: false,
              error: `Session '${to}' not found among active sessions`,
            }),
          },
        ],
      };
    }
  }

  const msgId = newMsgId();
  const now = new Date().toISOString();

  const doc: Message = {
    _id: msgId,
    from: SESSION_NAME!,
    to,
    content,
    meta: {
      type: "notification",
      sender_type: "agent",
      priority: "normal",
      ...meta,
    },
    status: "pending",
    created_at: now,
    delivered_at: null,
  };

  await messages.insertOne(doc);
  log("info", "Message sent", { msg_id: msgId, to, content_len: content.length });

  return {
    content: [
      { type: "text", text: JSON.stringify({ success: true, msg_id: msgId }) },
    ],
  };
}

async function handleGetTeamStatus() {
  const teamSessions = await sessions
    .find({ status: { $nin: ["completed", "closed"] } })
    .project({ _id: 1, name: 1, goal: 1, task: 1, status: 1, last_seen: 1 })
    .toArray();

  const now = Date.now();
  const members = teamSessions.map((s) => {
    const lastSeen = s.last_seen ? new Date(s.last_seen).getTime() : null;
    const stale =
      lastSeen === null || now - lastSeen > STALE_THRESHOLD_MS;
    const age = lastSeen
      ? `${Math.round((now - lastSeen) / 1000)}s ago`
      : "never";
    return {
      name: s.name,
      task: s.task || (s as any).goal || "",
      status: s.status,
      last_seen: age,
      stale,
    };
  });

  return {
    content: [
      { type: "text", text: JSON.stringify({ members }, null, 2) },
    ],
  };
}

async function handleGetMessages(args: Record<string, unknown>) {
  const limit = Math.min(Number(args.limit) || 20, 100);
  const since =
    (args.since as string) ||
    new Date(Date.now() - 30 * 60 * 1000).toISOString();

  // Returns both received AND sent messages — intentional for context recovery
  // after CC compacts older <channel> notifications from context
  const docs = await messages
    .find({
      $or: [{ to: SESSION_NAME }, { from: SESSION_NAME }],
      created_at: { $gt: since },
    })
    .sort({ created_at: -1 })
    .limit(limit)
    .toArray();

  const result = docs.map((d) => ({
    msg_id: d._id,
    from: d.from,
    to: d.to,
    content: d.content,
    meta: d.meta,
    status: d.status,
    created_at: d.created_at,
  }));

  return {
    content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
  };
}

// ── Delivery (cold path polling) ─────────────────────────────

async function deliverPending(): Promise<void> {
  try {
    const pending = await messages
      .find({ to: SESSION_NAME, status: "pending" })
      .sort({ created_at: 1 })
      .limit(10)
      .toArray();

    for (const msg of pending) {
      // Claim (not deliver) — atomically mark as "claimed" so other pollers skip it
      const claimed = await messages.findOneAndUpdate(
        { _id: msg._id, status: "pending" },
        { $set: { status: "claimed", claimed_by: SESSION_ID, claimed_at: new Date().toISOString() } }
      );
      if (!claimed) continue;

      if (deliveredSet.has(msg._id)) continue;

      try {
        await transport.deliver(msg.content, {
          from: msg.from,
          msg_id: msg._id,
          ...msg.meta,
        });

        // Delivery succeeded — mark as delivered
        deliveredSet.add(msg._id);
        await messages.updateOne(
          { _id: msg._id },
          { $set: { status: "delivered", delivered_at: new Date().toISOString() } }
        );

        log("info", "Delivered message", {
          msg_id: msg._id,
          from: msg.from,
        });
      } catch (deliverErr) {
        // Delivery failed — revert to pending so another poller can retry
        await messages.updateOne(
          { _id: msg._id, status: "claimed" },
          { $set: { status: "pending" }, $unset: { claimed_by: "", claimed_at: "" } }
        );
        const errMsg = deliverErr instanceof Error ? deliverErr.message : String(deliverErr);
        log("warn", "Delivery failed, reverted to pending", {
          msg_id: msg._id,
          error: errMsg,
        });
      }
    }
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    log("error", "Poll delivery failed", { error: errMsg });
  }
}

const STALE_CLAIM_MS = 10_000; // 10s — if claimed but not delivered, revert

async function recoverStaleClaims(): Promise<void> {
  try {
    const threshold = new Date(Date.now() - STALE_CLAIM_MS).toISOString();
    const result = await messages.updateMany(
      { to: SESSION_NAME, status: "claimed", claimed_at: { $lt: threshold } },
      { $set: { status: "pending" }, $unset: { claimed_by: "", claimed_at: "" } }
    );
    if (result.modifiedCount > 0) {
      log("info", "Recovered stale claims", { count: result.modifiedCount });
    }
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    log("error", "Stale claim recovery failed", { error: errMsg });
  }
}

// setTimeout recursion to prevent overlapping polls
async function pollLoop(): Promise<void> {
  await recoverStaleClaims();
  await deliverPending();
  setTimeout(pollLoop, POLL_INTERVAL_MS);
}

// ── Heartbeat ────────────────────────────────────────────────

function startHeartbeat(): void {
  setInterval(async () => {
    try {
      await sessions.updateOne(
        { _id: SESSION_ID },
        { $set: { last_seen: new Date().toISOString() } }
      );
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      log("error", "Heartbeat failed", { error: errMsg });
    }
  }, HEARTBEAT_INTERVAL_MS);
}

// ── Dedup set cleanup (prevent memory leak) ──────────────────

setInterval(() => {
  if (deliveredSet.size > 10_000) {
    deliveredSet.clear();
    log("info", "Cleared dedup set (overflow)");
  }
}, 60_000);

// ── Health HTTP endpoint ─────────────────────────────────────

const HEALTH_DIR = join(process.env.HOME || "/tmp", ".cortex", "health");
try { mkdirSync(HEALTH_DIR, { recursive: true }); } catch {}
const HEALTH_FILE = join(HEALTH_DIR, SESSION_ID || "unknown");
const startTime = Date.now();

const healthServer = createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      ok: true,
      session_id: SESSION_ID,
      session_name: SESSION_NAME,
      uptime_s: Math.round((Date.now() - startTime) / 1000),
    }));
  } else {
    res.writeHead(404);
    res.end();
  }
});

healthServer.listen(0, "127.0.0.1", () => {
  const port = (healthServer.address() as AddressInfo).port;
  writeFileSync(HEALTH_FILE, String(port));
  log("info", "Health endpoint started", { port, file: HEALTH_FILE });
});

// Clean up health file on exit
function cleanupHealthFile(): void {
  try { unlinkSync(HEALTH_FILE); } catch {}
}
process.on("exit", cleanupHealthFile);
process.on("SIGTERM", () => { cleanupHealthFile(); process.exit(0); });
process.on("SIGINT", () => { cleanupHealthFile(); process.exit(0); });

// ── Startup ──────────────────────────────────────────────────

log("info", "Starting channels MCP", {
  session_name: SESSION_NAME,
  session_id: SESSION_ID,
});

// Heartbeat can start immediately (writes to MongoDB, no MCP dependency)
startHeartbeat();

// Start delivery and polling AFTER MCP transport is connected
mcp.oninitialized = () => {
  log("info", "MCP initialized, signaling readiness");
  sessions.updateOne(
    { _id: SESSION_ID },
    { $set: { channel_status: "ready" } }
  ).catch((err) => {
    log("error", "Failed to set channel_status=ready", { error: String(err) });
  });

  // Delay first delivery — CC needs ~1s after oninitialized to set up its
  // conversation context. Without this, notifications are silently dropped.
  setTimeout(() => {
    log("info", "Readiness delay elapsed, starting message delivery");
    deliverPending().then(() => pollLoop()).catch((err) => {
      log("error", "Initial delivery failed", { error: String(err) });
      pollLoop();
    });
  }, 1000);
};

// Connect MCP (stdio transport)
const stdioTransport = new StdioServerTransport();
await mcp.connect(stdioTransport);
log("info", "MCP transport connected");

// Handle CC disconnect — stdin close means CC process died
process.stdin.on("end", async () => {
  log("info", "CC disconnected (stdin closed), marking offline");
  try {
    await sessions.updateOne(
      { _id: SESSION_ID },
      { $set: { channel_status: "offline" } }
    );
  } catch {
    // Best effort
  }
  process.exit(0);
});

// Keep process alive — heartbeat and polling intervals prevent exit
log("info", "MCP server running, waiting for messages");
