/**
 * Test: content size limit — messages > 10KB rejected.
 *
 * Spec ref: Known Constraints > Message content size limit
 * "Maximum message content: 10KB."
 *
 * Spec ref: MCP Tools > send_message (in index.ts)
 * if (content.length > MAX_CONTENT_SIZE) { return { success: false, error: ... } }
 */

import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { MongoClient, type Db } from "mongodb";
import { buildHandlers } from "../handlers";

const MAX_CONTENT_SIZE = 10_240;
const TEST_DB = "cortex_test_channels_ts_content";
const MONGO_URI = process.env.CORTEX_MONGODB_URI || "mongodb://localhost:27017";

let client: MongoClient;
let db: Db;
let handlers: ReturnType<typeof buildHandlers>;

beforeEach(async () => {
  client = new MongoClient(MONGO_URI);
  await client.connect();
  db = client.db(TEST_DB);
  handlers = buildHandlers(db, "test-session");

  await db.collection("session_registry").insertOne({
    _id: "sess-target",
    name: "target-session",
    team: "default",
    status: "active",
  });
});

afterEach(async () => {
  const cols = await db.listCollections().toArray();
  for (const col of cols) {
    await db.dropCollection(col.name);
  }
  await client.close();
});

describe("content size limit", () => {
  test("rejects message over 10KB", async () => {
    const oversized = "x".repeat(MAX_CONTENT_SIZE + 1);

    const result = await handlers.sendMessage({
      to: "target-session",
      content: oversized,
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(false);
    expect(parsed.error).toMatch(/10/);
  });

  test("accepts message at exactly 10KB", async () => {
    const atLimit = "x".repeat(MAX_CONTENT_SIZE);

    const result = await handlers.sendMessage({
      to: "target-session",
      content: atLimit,
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(true);
    expect(parsed.msg_id).toBeDefined();
  });

  test("accepts message under 10KB", async () => {
    const result = await handlers.sendMessage({
      to: "target-session",
      content: "Short message",
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(true);
  });

  test("oversized message not written to MongoDB", async () => {
    const oversized = "x".repeat(MAX_CONTENT_SIZE + 100);

    await handlers.sendMessage({ to: "target-session", content: oversized });

    const count = await db.collection("messages").countDocuments({ to: "target-session" });
    expect(count).toBe(0);
  });

  test("error message includes byte count", async () => {
    const oversized = "x".repeat(MAX_CONTENT_SIZE + 500);

    const result = await handlers.sendMessage({
      to: "target-session",
      content: oversized,
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.error).toContain(String(MAX_CONTENT_SIZE + 500));
  });

  test("accepts message just under 10KB", async () => {
    const underLimit = "x".repeat(MAX_CONTENT_SIZE - 1);

    const result = await handlers.sendMessage({
      to: "target-session",
      content: underLimit,
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(true);
  });
});
