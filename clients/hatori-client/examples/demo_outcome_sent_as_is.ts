import { respond, outcomeSentAsIs } from "../src/index.ts";

const run = async () => {
  const out = await respond({
    conversation_id: "reply:demo-thread",
    message_id: `reply:demo-msg-${Date.now()}`,
    sender_id: "reply:user",
    message: "Adj rövid választ.",
    metadata: { platform: "imessage" }
  });
  const ack = await outcomeSentAsIs({
    external_outcome_id: `reply:demo-outcome-${Date.now()}`,
    assistant_interaction_id: out.assistant_interaction_id,
    conversation_id: out.conversation_id,
    platform: "imessage",
  });
  console.log(ack);
};

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
