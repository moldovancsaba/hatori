import { health, ingestEvent, respond } from "../src/index.ts";

const run = async () => {
  console.log(await health());
  await ingestEvent({
    external_event_id: `reply:demo-ingest-${Date.now()}`,
    kind: "imessage",
    conversation_id: "reply:demo-thread",
    sender_id: "reply:user",
    content: "Szia! Ez egy demo üzenet.",
    metadata: { platform: "imessage" }
  });
  const out = await respond({
    conversation_id: "reply:demo-thread",
    message_id: `reply:demo-msg-${Date.now()}`,
    sender_id: "reply:user",
    message: "Kérlek adj rövid választ magyarul.",
    metadata: { platform: "imessage" }
  });
  console.log(out);
};

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
