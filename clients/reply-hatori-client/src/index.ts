import { createTwoFilesPatch } from "diff";

const BASE_URL = process.env.HATORI_BASE_URL || "http://127.0.0.1:8094";
const TOKEN = process.env.HATORI_API_TOKEN || "";

function headers() {
  return {
    "Content-Type": "application/json",
    "X-Hatori-Token": TOKEN,
  };
}

async function post(path: string, body: unknown) {
  const r = await fetch(`${BASE_URL}${path}`, { method: "POST", headers: headers(), body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${path} failed: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function health() {
  const r = await fetch(`${BASE_URL}/v1/health`);
  if (!r.ok) throw new Error(`health failed: ${r.status}`);
  return r.json();
}

export async function ingestEvent(body: Record<string, unknown>) {
  return post("/v1/ingest/event", body);
}

export async function respond(body: Record<string, unknown>) {
  return post("/v1/agent/respond", body);
}

export async function outcomeSentAsIs(args: {
  external_outcome_id: string;
  assistant_interaction_id: string;
  conversation_id?: string;
  platform?: string;
}) {
  return post("/v1/agent/outcome", {
    ...args,
    status: "sent_as_is",
  });
}

export function toUnifiedDiff(originalText: string, finalSentText: string) {
  return createTwoFilesPatch("original", "final", originalText, finalSentText, "", "", { context: 2 });
}

export async function outcomeEditedThenSent(args: {
  external_outcome_id: string;
  assistant_interaction_id: string;
  original_text: string;
  final_sent_text: string;
  edit_reason?: string;
  conversation_id?: string;
  platform?: string;
}) {
  return post("/v1/agent/outcome", {
    ...args,
    status: "edited_then_sent",
    diff: toUnifiedDiff(args.original_text, args.final_sent_text),
  });
}
