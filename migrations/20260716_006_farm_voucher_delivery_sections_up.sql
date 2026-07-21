BEGIN;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  ADD COLUMN IF NOT EXISTS delivery_sections jsonb NOT NULL DEFAULT '[]'::jsonb;

UPDATE pipkgfu2wr9qxyy.business_os_voucher_draft draft
SET delivery_sections = jsonb_build_array(
  jsonb_build_object(
    'delivery_date', draft.voucher_date,
    'items', COALESCE((
      SELECT jsonb_agg(
        (line.value - 'description' - 'item') || jsonb_build_object(
          'crop_id', NULL,
          'custom_description', COALESCE(NULLIF(line.value->>'description', ''), line.value->>'item', ''),
          'note', COALESCE(line.value->>'note', '')
        )
        ORDER BY line.ordinality
      )
      FROM jsonb_array_elements(draft.lines) WITH ORDINALITY AS line(value, ordinality)
    ), '[]'::jsonb)
  )
)
WHERE draft.sector = 'farm'
  AND draft.delivery_sections = '[]'::jsonb
  AND jsonb_typeof(draft.lines) = 'array'
  AND jsonb_array_length(draft.lines) > 0;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP CONSTRAINT IF EXISTS business_os_voucher_draft_delivery_sections_array;
ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  ADD CONSTRAINT business_os_voucher_draft_delivery_sections_array
  CHECK (jsonb_typeof(delivery_sections) = 'array');

COMMIT;
