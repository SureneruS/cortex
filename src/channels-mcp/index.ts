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
  status: "pending" | "delivered";
  created_at: string;
  delivered_at: string | null;
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

if (!SESSION_NAME || !SESSION_ID || !MONGODB_URI) {
  process.stderr.write(
    "[cortex-team] FATAL: CORTEX_SESSION_NAME, CORTEX_SESSION_ID, and CORTEX_MONGODB_URI are required\n"
  );
  process.exit(1);
}

// ── Logging ──────────────────────────────────────────────────

import { appendFileSync, mkdirSync } from "fs";
import { join } from "path";

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

const INSTRUCTIONS = `Messages from other sessions arrive AUTOMATICALLY as <channel source="cortex-team" from="..." type="..." ...> notifications. You do NOT need to poll for them — they are pushed into your context between turns.

Use send_message to communicate with other sessions or the human operator.
Use get_status to see who's active and what they're working on.
Use get_messages ONLY to recover messages you might have missed (e.g. after context compaction). Do NOT use it to wait for replies — replies arrive as channel notifications automatically.

When you receive a message while working:
- If it's relevant to your current task, incorporate it immediately
- If you're blocked on something you asked about, handle the reply before continuing
- If it's unrelated to your current task, acknowledge it and handle after your current step
- If it mentions "stop", "wrong", or "revert", pause and address it

When you receive a lifecycle message (meta.type="lifecycle", meta.action="wrapup"):
1. Acknowledge receipt via send_message to the sender
2. Run /session-wrapup to save your learnings
3. Update your session status: cortex session update <your_session_id> --data '{"status": "completed"}' --trigger wrapup
4. Exit with /exit

Messages are async. Don't wait for replies — continue your work.
When you discover new tasks or blockers, report them via send_message.
If you need a new session for a subtask, you can spawn one with cortex session spawn.
To reach the human, use send_message(to="human", ...) — it will be delivered to Slack.`;

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
      status: { $nin: ["completed", "dead"] },
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
    .find({ status: { $nin: ["completed", "dead"] } })
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
      const claimed = await messages.findOneAndUpdate(
        { _id: msg._id, status: "pending" },
        { $set: { status: "delivered", delivered_at: new Date().toISOString() } }
      );
      if (!claimed) continue;

      if (deliveredSet.has(msg._id)) continue;
      deliveredSet.add(msg._id);

      await transport.deliver(msg.content, {
        from: msg.from,
        msg_id: msg._id,
        ...msg.meta,
      });

      log("info", "Delivered message", {
        msg_id: msg._id,
        from: msg.from,
      });
    }
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    log("error", "Poll delivery failed", { error: errMsg });
  }
}

// setTimeout recursion to prevent overlapping polls
async function pollLoop(): Promise<void> {
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

// ── Startup ──────────────────────────────────────────────────

log("info", "Starting channels MCP", {
  session_name: SESSION_NAME,
  session_id: SESSION_ID,
});

// Heartbeat can start immediately (writes to MongoDB, no MCP dependency)
startHeartbeat();

// Start delivery and polling AFTER MCP transport is connected
mcp.oninitialized = () => {
  log("info", "MCP initialized, starting message delivery");
  deliverPending().then(() => pollLoop()).catch((err) => {
    log("error", "Initial delivery failed", { error: String(err) });
    pollLoop();
  });
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
