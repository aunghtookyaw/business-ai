-- Add user-friendly generated code fields for master tables.
-- These columns are generated from the existing auto-number primary key.
-- Existing record values are not manually updated or deleted.

ALTER TABLE pipkgfu2wr9qxyy.customer_master
ADD COLUMN IF NOT EXISTS "Customer_Code" text
GENERATED ALWAYS AS ('CUS-' || lpad(id::text, 4, '0')) STORED;

ALTER TABLE pipkgfu2wr9qxyy.category_master
ADD COLUMN IF NOT EXISTS "Category_Code" text
GENERATED ALWAYS AS (
    CASE
        WHEN lower(coalesce(category_name, '')) LIKE '%labor%'
            OR lower(coalesce(category_name, '')) LIKE '%labour%'
            THEN 'LAB-'
        WHEN lower(coalesce(category_name, '')) LIKE '%supplier%'
            THEN 'SUP-'
        ELSE 'CAT-'
    END || lpad(id::text, 4, '0')
) STORED;

ALTER TABLE pipkgfu2wr9qxyy.fixed_assests
ADD COLUMN IF NOT EXISTS "Asset_Code" text
GENERATED ALWAYS AS ('AST-' || lpad(id::text, 4, '0')) STORED;
