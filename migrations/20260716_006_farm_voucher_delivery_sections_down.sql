BEGIN;

UPDATE pipkgfu2wr9qxyy.business_os_voucher_draft draft
SET lines = COALESCE((
  SELECT jsonb_agg(
    (item.value - 'custom_description' - 'crop_name') || jsonb_build_object(
      'description', COALESCE(NULLIF(item.value->>'crop_name', ''), item.value->>'custom_description', ''),
      'delivery_date', section.value->>'delivery_date'
    )
    ORDER BY section.ordinality, item.ordinality
  )
  FROM jsonb_array_elements(draft.delivery_sections) WITH ORDINALITY AS section(value, ordinality)
  CROSS JOIN LATERAL jsonb_array_elements(section.value->'items') WITH ORDINALITY AS item(value, ordinality)
), draft.lines)
WHERE draft.sector = 'farm' AND jsonb_array_length(draft.delivery_sections) > 0;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP CONSTRAINT IF EXISTS business_os_voucher_draft_delivery_sections_array;
ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP COLUMN IF EXISTS delivery_sections;

COMMIT;
