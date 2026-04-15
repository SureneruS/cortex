/**
 * Testable handler functions extracted from index.ts.
 *
 * This module exports `buildHandlers(db, sessionName)` so tests can inject
 * a test database and verify behavior without running the full MCP server.
 *
 * index.ts calls buildHandlers(db, SESSION_NAME) and wires the results into
 * the MCP request handler.
 */

import type { Db } from "mongodb";

import {
  AGENT_SENDER_TYPE,
  canonicalRecipient,
  isHumanRecipient,
} from "./routing.js";

export interface Transport {
  deliver(content: string, meta: Record<string, string>): Promise<void>;
}

export interface ToolResult {
  content: [{ type: "text"; text: string }];
  isError?: boolean;
}

const MAX_CONTENT_SIZE = 10_240;
const META_KEY_RE = /^[a-zA-Z0-9_]+$/;

function newMsgId(): string {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  return "msg_" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function ok(data: unknown): ToolResult {
  return { content: [{ type: "text", text: JSON.stringify(data) }] };
}

function err(error: string): ToolResult {
  return { content: [{ type: "text", text: JSON.stringify({ success: false, error }) }] };
}

export function buildHandlers(db: Db, sessionName: string, sessionId?: string) {
  const messages = db.collection<any>("messages");
  const sessions = db.collection<any>("session_registry");
  const deliveredSet = new Set<string>();

  async function ensureIndexes(): Promise<void> {
    await messages.createIndex(
      { to: 1, status: 1, created_at: 1 },
      { name: "poll_query" }
    );
    await messages.createIndex(
      { created_at: 1 },
      { name: "ttl_cleanup", expireAfterSeconds: 7 * 24 * 60 * 60 }
    );
  }

  async function sendMessage(args: {
    to: string;
    content: string;
    meta?: Record<string, string>;
  }): Promise<ToolResult> {
    const { to, content, meta = {} } = args;

    if (!to) return err("Missing 'to' field");
    if (!content) return err("Missing 'content' field");
    if (content.length > MAX_CONTENT_SIZE) {
      return err(
        `Content exceeds ${MAX_CONTENT_SIZE} byte limit (${content.length} bytes)`
      );
    }

    const { canonical, warning } = canonicalRecipient(to);

    if (!isHumanRecipient(canonical)) {
      const target = await sessions.findOne({
        name: canonical,
        status: { $nin: ["completed", "closed"] },
      });
      if (!target) {
        return err(`Session '${canonical}' not found among active sessions`);
      }
    }

    const msgId = newMsgId();
    const now = new Date().toISOString();

    const doc = {
      _id: msgId,
      from: sessionName,
      to: canonical,
      content,
      meta: {
        type: "notification",
        sender_type: AGENT_SENDER_TYPE,
        priority: "normal",
        ...meta,
      },
      status: "pending" as const,
      created_at: now,
      delivered_at: null,
    };

    await messages.insertOne(doc);
    const payload: Record<string, unknown> = { success: true, msg_id: msgId };
    if (warning) payload.warning = warning;
    return ok(payload);
  }

  async function deliverPending(transport: Transport): Promise<void> {
    try {
      const pending = await messages
        .find({ to: sessionName, status: "pending" })
        .sort({ created_at: 1 })
        .limit(10)
        .toArray();

      for (const msg of pending) {
        const claimed = await messages.findOneAndUpdate(
          { _id: msg._id, status: "pending" },
          { $set: { status: "claimed", claimed_by: sessionId || sessionName, claimed_at: new Date().toISOString() } }
        );
        if (!claimed) continue;

        if (deliveredSet.has(msg._id)) continue;

        try {
          await transport.deliver(msg.content, {
            from: msg.from,
            msg_id: msg._id,
            ...msg.meta,
          });

          deliveredSet.add(msg._id);
          await messages.updateOne(
            { _id: msg._id },
            { $set: { status: "delivered", delivered_at: new Date().toISOString() } }
          );
        } catch {
          await messages.updateOne(
            { _id: msg._id, status: "claimed" },
            { $set: { status: "pending" }, $unset: { claimed_by: "", claimed_at: "" } }
          );
        }
      }
    } catch {
      // Log and continue — poll failure must not crash the server
    }
  }

  async function getStatus(): Promise<ToolResult> {
    const STALE_THRESHOLD_MS = 5 * 60 * 1000;
    const allSessions = await sessions
      .find({ status: { $nin: ["completed", "closed"] } })
      .project({ _id: 1, name: 1, goal: 1, task: 1, status: 1, last_seen: 1 })
      .toArray();

    const now = Date.now();
    const members = allSessions.map((s: any) => {
      const lastSeen = s.last_seen ? new Date(s.last_seen).getTime() : null;
      const stale = lastSeen === null || now - lastSeen > STALE_THRESHOLD_MS;
      const age = lastSeen ? `${Math.round((now - lastSeen) / 1000)}s ago` : "never";
      return { name: s.name, task: s.task || s.goal || "", status: s.status, last_seen: age, stale };
    });

    return ok({ members });
  }

  async function getMessages(args: {
    limit?: number;
    since?: string;
  }): Promise<ToolResult> {
    const limit = Math.min(Number(args.limit) || 20, 100);
    const since =
      args.since || new Date(Date.now() - 30 * 60 * 1000).toISOString();

    const docs = await messages
      .find({
        $or: [{ to: sessionName }, { from: sessionName }],
        created_at: { $gt: since },
      })
      .sort({ created_at: -1 })
      .limit(limit)
      .toArray();

    const result = docs.map((d: any) => ({
      msg_id: d._id,
      from: d.from,
      to: d.to,
      content: d.content,
      meta: d.meta,
      status: d.status,
      created_at: d.created_at,
    }));

    return ok(result);
  }

  return { sendMessage, deliverPending, getStatus, getMessages, ensureIndexes };
}
