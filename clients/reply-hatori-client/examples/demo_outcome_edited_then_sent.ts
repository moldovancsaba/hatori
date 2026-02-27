import { respond, outcomeEditedThenSent } from "../src/index.ts";

const run = async () => {
  const out = await respond({
    conversation_id: "reply:demo-thread",
    message_id: `reply:demo-msg-${Date.now()}`,
    sender_id: "reply:user",
    message: "Adj rövid, barátságos választ.",
    metadata: { platform: "imessage" }
  });
  const finalSent = "Szia! Persze, segítek, mondd nyugodtan.";
  const ack = await outcomeEditedThenSent({
    external_outcome_id: `reply:demo-outcome-edited-${Date.now()}`,
    assistant_interaction_id: out.assistant_interaction_id,
    conversation_id: out.conversation_id,
    platform: "imessage",
    original_text: out.assistant_message,
    final_sent_text: finalSent,
    edit_reason: "shorter + warmer",
  });
  console.log(ack);
};

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
