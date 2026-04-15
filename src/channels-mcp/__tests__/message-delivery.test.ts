/**
 * Test: send_message tool — MongoDB write and validation.
 *
 * Spec ref: MCP Tools > send_message
 * - Validates recipient against session registry
 * - Writes message to MongoDB with status: "pending"
 * - Returns { success: true, msg_id } or { success: false, error: "..." }
 */

import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { MongoClient, type Db } from "mongodb";
import { buildHandlers } from "../handlers";

const TEST_DB = "cortex_test_channels_ts";
const MONGO_URI = process.env.CORTEX_MONGODB_URI || "mongodb://localhost:27017";

let client: MongoClient;
let db: Db;
let handlers: ReturnType<typeof buildHandlers>;

beforeEach(async () => {
  client = new MongoClient(MONGO_URI);
  await client.connect();
  db = client.db(TEST_DB);
  handlers = buildHandlers(db, "test-session");
  await handlers.ensureIndexes();
});

afterEach(async () => {
  const cols = await db.listCollections().toArray();
  for (const col of cols) {
    await db.dropCollection(col.name);
  }
  await client.close();
});

describe("send_message", () => {
  test("writes message to MongoDB with status pending", async () => {
    await db.collection("session_registry").insertOne({
      _id: "sess-target",
      name: "feedback-endpoint",
      team: "default",
      task: "implement feedback",
      status: "active",
      last_seen: new Date().toISOString(),
    });

    const result = await handlers.sendMessage({
      to: "feedback-endpoint",
      content: "Schema is ready. POST /api/feedback",
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(true);
    expect(parsed.msg_id).toBeDefined();

    const doc = await db.collection("messages").findOne({ _id: parsed.msg_id });
    expect(doc).not.toBeNull();
    expect(doc!.status).toBe("pending");
    expect(doc!.to).toBe("feedback-endpoint");
    expect(doc!.content).toBe("Schema is ready. POST /api/feedback");
    expect(doc!.delivered_at).toBeNull();
  });

  test("stores from field at top level", async () => {
    await db.collection("session_registry").insertOne({
      _id: "sess-t",
      name: "target-session",
      team: "default",
      status: "active",
    });

    const result = await handlers.sendMessage({
      to: "target-session",
      content: "Hello",
    });

    const { msg_id } = JSON.parse(result.content[0].text);
    const doc = await db.collection("messages").findOne({ _id: msg_id });
    expect(doc!.from).toBe("test-session");
  });

  test("stores meta fields with defaults", async () => {
    await db.collection("session_registry").insertOne({
      _id: "sess-meta",
      name: "meta-session",
      team: "default",
      status: "active",
    });

    const result = await handlers.sendMessage({
      to: "meta-session",
      content: "Test",
      meta: { type: "request", priority: "high", thread_id: "t_abc" },
    });

    const { msg_id } = JSON.parse(result.content[0].text);
    const doc = await db.collection("messages").findOne({ _id: msg_id });
    expect(doc!.meta.type).toBe("request");
    expect(doc!.meta.priority).toBe("high");
    expect(doc!.meta.thread_id).toBe("t_abc");
    expect(doc!.meta.sender_type).toBe("agent");
  });

  test("returns error for non-existent session", async () => {
    const result = await handlers.sendMessage({
      to: "nonexistent-session",
      content: "Hello",
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(false);
    expect(parsed.error).toContain("nonexistent-session");
  });

  test("returns error for completed session", async () => {
    await db.collection("session_registry").insertOne({
      _id: "sess-done",
      name: "completed-session",
      team: "default",
      status: "completed",
    });

    const result = await handlers.sendMessage({
      to: "completed-session",
      content: "Hello",
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(false);
  });

  test("does not write to MongoDB on validation failure", async () => {
    await handlers.sendMessage({ to: "ghost-session", content: "hello" });

    const count = await db.collection("messages").countDocuments({ to: "ghost-session" });
    expect(count).toBe(0);
  });

  test("suren reserved keyword bypasses session validation", async () => {
    const result = await handlers.sendMessage({
      to: "suren",
      content: "Please review",
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(true);
    expect(parsed.warning).toBeUndefined();

    const doc = await db.collection("messages").findOne({ to: "suren" });
    expect(doc).not.toBeNull();
    expect(doc!.status).toBe("pending");
  });

  test("legacy 'human' recipient is coerced to 'suren' with a warning", async () => {
    const result = await handlers.sendMessage({
      to: "human",
      content: "Please review",
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(true);
    expect(parsed.warning).toBeDefined();
    expect(parsed.warning).toContain("deprecated");

    const surenDoc = await db.collection("messages").findOne({ to: "suren" });
    expect(surenDoc).not.toBeNull();
    const humanDoc = await db.collection("messages").findOne({ to: "human" });
    expect(humanDoc).toBeNull();
  });
});
