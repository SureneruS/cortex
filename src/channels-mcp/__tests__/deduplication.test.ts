/**
 * Test: message deduplication — atomic claim + in-process dedup set.
 *
 * Spec ref: Channels MCP Server > Message Deduplication
 * "MCP tracks delivered msg_id values in-process (a Set<string>)."
 * "Combined with atomic findOneAndUpdate (status: 'pending' → 'delivered') to prevent
 * concurrent delivery."
 *
 * Spec ref: Polling Loop
 * "If findOneAndUpdate returns null (already claimed by concurrent process): skip silently"
 */

import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { MongoClient, type Db } from "mongodb";
import { buildHandlers } from "../handlers";

const TEST_DB = "cortex_test_channels_ts_dedup";
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

describe("deduplication", () => {
  test("concurrent deliverPending calls deliver each message exactly once", async () => {
    await db.collection("messages").insertMany(
      Array.from({ length: 5 }, (_, i) => ({
        _id: `msg_conc_${String(i).padStart(3, "0")}`,
        from: "sender",
        to: "my-session",
        content: `message ${i}`,
        meta: { type: "notification", sender_type: "agent", priority: "normal" },
        status: "pending",
        created_at: `2026-03-26T10:0${i}:00.000Z`,
        delivered_at: null,
      }))
    );

    const delivered: string[] = [];
    const handlers1 = buildHandlers(db, "my-session");
    const handlers2 = buildHandlers(db, "my-session");

    await Promise.all([
      handlers1.deliverPending({ deliver: async (c) => { delivered.push(c); } }),
      handlers2.deliverPending({ deliver: async (c) => { delivered.push(c); } }),
    ]);

    const unique = new Set(delivered);
    expect(unique.size).toBe(delivered.length);
    expect(delivered.length).toBe(5);
  });

  test("already-delivered message not re-delivered on second poll", async () => {
    await db.collection("messages").insertOne({
      _id: "msg_dedup_single",
      from: "sender",
      to: "my-session",
      content: "Important",
      meta: {},
      status: "pending",
      created_at: new Date().toISOString(),
      delivered_at: null,
    });

    const delivered: string[] = [];
    const handlers = buildHandlers(db, "my-session");

    await handlers.deliverPending({ deliver: async (c) => { delivered.push(c); } });
    await handlers.deliverPending({ deliver: async (c) => { delivered.push(c); } });

    expect(delivered).toHaveLength(1);
  });

  test("in-process dedup set blocks duplicate delivery", async () => {
    await db.collection("messages").insertOne({
      _id: "msg_inproc_001",
      from: "sender",
      to: "my-session",
      content: "Once only",
      meta: {},
      status: "pending",
      created_at: new Date().toISOString(),
      delivered_at: null,
    });

    const delivered: string[] = [];
    const handlers = buildHandlers(db, "my-session");
    const transport = { deliver: async (c: string) => { delivered.push(c); } };

    await handlers.deliverPending(transport);

    // Force the document back to pending to simulate DB inconsistency
    await db.collection("messages").updateOne(
      { _id: "msg_inproc_001" },
      { $set: { status: "pending" } }
    );

    // In-process set should prevent re-delivery
    await handlers.deliverPending(transport);

    expect(delivered).toHaveLength(1);
  });

  test("all messages delivered across multiple poll cycles", async () => {
    for (let i = 0; i < 3; i++) {
      await db.collection("messages").insertOne({
        _id: `msg_cycle_${i}`,
        from: "sender",
        to: "my-session",
        content: `msg ${i}`,
        meta: {},
        status: "pending",
        created_at: new Date().toISOString(),
        delivered_at: null,
      });
    }

    const delivered: string[] = [];
    const handlers = buildHandlers(db, "my-session");

    for (let cycle = 0; cycle < 3; cycle++) {
      await handlers.deliverPending({ deliver: async (c) => { delivered.push(c); } });
    }

    expect(delivered).toHaveLength(3);
  });
});
