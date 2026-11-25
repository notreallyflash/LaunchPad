-- LaunchPad: application-facing ESCO tables.
--
-- This schema is designed for the columns queried by:
--   sql/02_resolve_esco_skill_labels.sql
--   sql/03_rank_esco_occupations.sql
--
-- It creates empty tables and indexes. It does NOT download or import the
-- official ESCO dataset. See README.md for the ESCO CSV import mapping.

BEGIN;

CREATE TABLE IF NOT EXISTS public.esco_skills (
    skill_uri       text PRIMARY KEY,
    preferred_label text NOT NULL,
    skill_type      text,
    reuse_level     text
);

CREATE TABLE IF NOT EXISTS public.esco_skill_labels (
    normalized_label text NOT NULL,
    skill_uri        text NOT NULL
        REFERENCES public.esco_skills (skill_uri)
        ON DELETE CASCADE,
    label            text NOT NULL,
    label_type       text NOT NULL
        CHECK (label_type IN ('preferred', 'alternative', 'hidden')),
    CONSTRAINT esco_skill_labels_unique_label_per_skill
        UNIQUE (normalized_label, skill_uri, label_type)
);

CREATE TABLE IF NOT EXISTS public.esco_occupations (
    occupation_uri   text PRIMARY KEY,
    preferred_label  text NOT NULL,
    isco_group_code  text,
    isco_major_group text
);

CREATE TABLE IF NOT EXISTS public.esco_occupation_skill_relations (
    occupation_uri text NOT NULL
        REFERENCES public.esco_occupations (occupation_uri)
        ON DELETE CASCADE,
    skill_uri text NOT NULL
        REFERENCES public.esco_skills (skill_uri)
        ON DELETE CASCADE,
    relation_type text NOT NULL
        CHECK (relation_type IN ('essential', 'optional')),
    PRIMARY KEY (occupation_uri, skill_uri, relation_type)
);

-- Exact-label lookup and URI joins used by the recognition pipeline.
CREATE INDEX IF NOT EXISTS esco_skill_labels_normalized_label_idx
    ON public.esco_skill_labels (normalized_label);

CREATE INDEX IF NOT EXISTS esco_skill_labels_skill_uri_idx
    ON public.esco_skill_labels (skill_uri);

CREATE INDEX IF NOT EXISTS esco_occupation_skill_relations_skill_uri_idx
    ON public.esco_occupation_skill_relations (skill_uri);

CREATE INDEX IF NOT EXISTS esco_occupations_isco_major_group_idx
    ON public.esco_occupations (isco_major_group);

-- The RPC functions use SECURITY INVOKER / the caller's privileges.
-- Grant read-only access to the reference tables for the API roles.
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT ON TABLE
    public.esco_skills,
    public.esco_skill_labels,
    public.esco_occupations,
    public.esco_occupation_skill_relations
TO anon, authenticated;

COMMENT ON TABLE public.esco_skills IS
    'Canonical ESCO skill and knowledge concepts used by LaunchPad.';
COMMENT ON TABLE public.esco_skill_labels IS
    'One row per preferred, alternative or hidden label mapped to an ESCO skill URI.';
COMMENT ON TABLE public.esco_occupations IS
    'ESCO occupation concepts with ISCO-08 group metadata.';
COMMENT ON TABLE public.esco_occupation_skill_relations IS
    'ESCO occupation-to-skill relationships classified as essential or optional.';

COMMIT;
