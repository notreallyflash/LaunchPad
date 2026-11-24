-- LaunchPad AI: indexed ESCO skill-label lookup RPC.
-- Run this once in Supabase SQL Editor after the six ESCO tables are imported.
-- This function only reads the public ESCO reference tables.

create or replace function public.resolve_esco_skill_labels(
    p_normalized_labels text[]
)
returns table (
    normalized_label text,
    skill_uri text,
    label text,
    label_type text,
    preferred_label text,
    skill_type text,
    reuse_level text
)
language sql
stable
security invoker
set search_path = public, pg_temp
as $$
    select
        l.normalized_label,
        l.skill_uri,
        l.label,
        l.label_type,
        s.preferred_label,
        s.skill_type,
        s.reuse_level
    from public.esco_skill_labels as l
    join public.esco_skills as s
        on s.skill_uri = l.skill_uri
    where l.normalized_label = any(
        coalesce(p_normalized_labels, array[]::text[])
    );
$$;

grant execute on function public.resolve_esco_skill_labels(text[])
to anon, authenticated;

comment on function public.resolve_esco_skill_labels(text[])
is 'Returns exact ESCO skill-label matches for supplied normalized phrases; ambiguous labels are returned as multiple URI rows for application-side review.';
