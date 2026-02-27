BEGIN;

CREATE TABLE IF NOT EXISTS delivery_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_outcome_id text NOT NULL UNIQUE,
  assistant_interaction_id uuid NOT NULL REFERENCES interaction_events(id) ON DELETE RESTRICT,
  status text NOT NULL,
  platform text NULL,
  recipient_id text NULL,
  conversation_id text NULL,
  original_text text NULL,
  final_sent_text text NULL,
  diff text NULL,
  edit_reason text NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_delivery_events_assistant_interaction_id
  ON delivery_events(assistant_interaction_id);
CREATE INDEX IF NOT EXISTS idx_delivery_events_occurred_at_desc
  ON delivery_events(occurred_at DESC);

COMMIT;
