-- Outcome-learning foundation: structured founder labels and the evidence
-- snapshot attached to each automatically shipped clip.

alter table clips
  add column if not exists feedback_reason text,
  add column if not exists feedback_at timestamptz,
  add column if not exists selection_meta jsonb not null default '{}';

alter table clips drop constraint if exists clips_feedback_reason_check;
alter table clips add constraint clips_feedback_reason_check check (
  feedback_reason is null or feedback_reason in (
    'good_as_is',
    'weak_moment',
    'missing_context',
    'cause_not_visible',
    'slow_or_redundant',
    'starts_late',
    'ends_early',
    'bad_title',
    'bad_framing',
    'technical',
    'other'
  )
);

create index if not exists clips_feedback_learning_idx
  on clips (feedback_at desc)
  where feedback is not null;
