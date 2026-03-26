/**
 * Test: offline delivery — pending messages delivered on MCP startup.
 *
 * Spec ref: Channels MCP Server > Startup Sequence
 * "4. Deliver all pending messages (one-time initial delivery before poll loop starts)."
 *
 * Spec ref: Communication Model > Offline delivery
 * "Messages persist in MongoDB. If the recipient is offline, messages queue until they
 * start a new session and the MCP polls for pending messages."
 */

import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { MongoClient, type Db } from "mongodb";
import { buildHandlers, type Transport } from "../handlers";

const TEST_DB = "cortex_test_channels_ts_offline";
const MONGO_URI = process.env.CORTEX_MONGODB_URI || "mongodb://localhost:27017";

let client: MongoClient;
let db: Db;

beforeEach(async () => {
  client = new MongoClient(MONGO_URI);
  await client.connect();
  db = client.db(TEST_DB);
});

afterEach(async () => {
  const cols = await db.listCollections().toArray();
  for (const col of cols) {
    await db.dropCollection(col.name);
  }
  await client.close();
});

describe("offline queue", () => {
  test("pending messages are delivered on startup", async () => {
    const delivered: Array<{ content: string; meta: Record<string, string> }> = [];

    await db.collection("messages").insertMany([
      {
        _id: "msg_offline_001",
        from: "auth-refactor",
        to: "my-session",
        content: "Schema is ready",
        meta: { type: "notification", sender_type: "agent", priority: "normal" },
        status: "pending",
        created_at: "2026-03-26T09:00:00.000Z",
        delivered_at: null,
      },
      {
        _id: "msg_offline_002",
        from: "other-session",
        to: "my-session",
        content: "PR review done",
        meta: { type: "notification", sender_type: "agent", priority: "normal" },
        status: "pending",
        created_at: "2026-03-26T09:01:00.000Z",
        delivered_at: null,
      },
    ]);

    const mockTransport: Transport = {
      deliver: async (content, meta) => {
        delivered.push({ content, meta });
      },
    };

    const handlers = buildHandlers(db, "my-session");
    await handlers.deliverPending(mockTransport);

    expect(delivered).toHaveLength(2);
    expect(delivered.map((d) => d.content)).toContain("Schema is ready");
    expect(delivered.map((d) => d.content)).toContain("PR review done");
  });

  test("startup delivery marks messages as delivered in MongoDB", async () => {
    await db.collection("messages").insertOne({
      _id: "msg_startup_001",
      from: "sender",
      to: "my-session",
      content: "Hello",
      meta: { type: "notification", sender_type: "agent", priority: "normal" },
      status: "pending",
      created_at: new Date().toISOString(),
      delivered_at: null,
    });

    const handlers = buildHandlers(db, "my-session");
    await handlers.deliverPending({ deliver: async () => {} });

    const doc = await db.collection("messages").findOne({ _id: "msg_startup_001" });
    expect(doc!.status).toBe("delivered");
    expect(doc!.delivered_at).not.toBeNull();
  });

  test("messages for other sessions not delivered to this session", async () => {
    await db.collection("messages").insertOne({
      _id: "msg_other_001",
      from: "sender",
      to: "other-session",
      content: "Not for me",
      meta: {},
      status: "pending",
      created_at: new Date().toISOString(),
      delivered_at: null,
    });

    const delivered: string[] = [];
    const handlers = buildHandlers(db, "my-session");
    await handlers.deliverPending({
      deliver: async (content) => {
        delivered.push(content);
      },
    });

    expect(delivered).toHaveLength(0);

    const doc = await db.collection("messages").findOne({ _id: "msg_other_001" });
    expect(doc!.status).toBe("pending");
  });

  test("offline messages include from field in notification meta", async () => {
    await db.collection("messages").insertOne({
      _id: "msg_meta_001",
      from: "auth-refactor",
      to: "my-session",
      content: "Update",
      meta: { type: "notification", sender_type: "agent", priority: "normal" },
      status: "pending",
      created_at: new Date().toISOString(),
      delivered_at: null,
    });

    const delivered: Array<{ content: string; meta: Record<string, string> }> = [];
    const handlers = buildHandlers(db, "my-session");
    await handlers.deliverPending({
      deliver: async (content, meta) => {
        delivered.push({ content, meta });
      },
    });

    expect(delivered[0].meta.from).toBe("auth-refactor");
    expect(delivered[0].meta.msg_id).toBe("msg_meta_001");
  });

  test("delivery is ordered oldest first", async () => {
    await db.collection("messages").insertMany([
      {
        _id: "msg_order_002",
        from: "b",
        to: "my-session",
        content: "second",
        meta: {},
        status: "pending",
        created_at: "2026-03-26T10:01:00.000Z",
        delivered_at: null,
      },
      {
        _id: "msg_order_001",
        from: "a",
        to: "my-session",
        content: "first",
        meta: {},
        status: "pending",
        created_at: "2026-03-26T10:00:00.000Z",
        delivered_at: null,
      },
    ]);

    const order: string[] = [];
    const handlers = buildHandlers(db, "my-session");
    await handlers.deliverPending({
      deliver: async (content) => {
        order.push(content);
      },
    });

    expect(order[0]).toBe("first");
    expect(order[1]).toBe("second");
  });
});
