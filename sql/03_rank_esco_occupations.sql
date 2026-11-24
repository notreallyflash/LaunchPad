
CREATE OR REPLACE FUNCTION public.rank_esco_occupations(
    p_matched_skill_uris text[],
    p_isco_major_groups text[] DEFAULT ARRAY['1', '2', '3', '4', '5']::text[],
    p_min_matched_essential integer DEFAULT 2,
    p_include_all boolean DEFAULT false
)
RETURNS TABLE (
    occupation_uri text,
    occupation_label text,
    isco_group_code text,
    isco_major_group text,
    matched_essential integer,
    total_essential integer,
    essential_coverage numeric,
    matched_optional integer,
    total_optional integer,
    weighted_skill_coverage numeric
)
LANGUAGE sql
STABLE
AS $function$
    WITH candidate_skills AS (
        SELECT DISTINCT
            UNNEST(COALESCE(p_matched_skill_uris, ARRAY[]::text[])) AS skill_uri
    ),
    scored AS (
        SELECT
            o.occupation_uri,
            o.preferred_label,
            o.isco_group_code,
            o.isco_major_group,

            COUNT(*) FILTER (
                WHERE r.relation_type = 'essential'
            )::integer AS total_essential,

            COUNT(*) FILTER (
                WHERE r.relation_type = 'essential'
                  AND cs.skill_uri IS NOT NULL
            )::integer AS matched_essential,

            COUNT(*) FILTER (
                WHERE r.relation_type = 'optional'
            )::integer AS total_optional,

            COUNT(*) FILTER (
                WHERE r.relation_type = 'optional'
                  AND cs.skill_uri IS NOT NULL
            )::integer AS matched_optional,

            SUM(
                (CASE
                    WHEN r.relation_type = 'essential' THEN 3.0
                    ELSE 1.0
                END) *
                (CASE s.reuse_level
                    WHEN 'occupation-specific' THEN 1.0
                    WHEN 'sector-specific' THEN 1.0
                    WHEN 'cross-sector' THEN 0.6
                    WHEN 'transversal' THEN 0.25
                    ELSE 0.5
                END)
            ) FILTER (
                WHERE cs.skill_uri IS NOT NULL
            ) AS weighted_matched,

            SUM(
                (CASE
                    WHEN r.relation_type = 'essential' THEN 3.0
                    ELSE 1.0
                END) *
                (CASE s.reuse_level
                    WHEN 'occupation-specific' THEN 1.0
                    WHEN 'sector-specific' THEN 1.0
                    WHEN 'cross-sector' THEN 0.6
                    WHEN 'transversal' THEN 0.25
                    ELSE 0.5
                END)
            ) AS weighted_total

        FROM public.esco_occupation_skill_relations r
        JOIN public.esco_occupations o
            ON o.occupation_uri = r.occupation_uri
        JOIN public.esco_skills s
            ON s.skill_uri = r.skill_uri
        LEFT JOIN candidate_skills cs
            ON cs.skill_uri = r.skill_uri

        WHERE p_include_all
           OR o.isco_major_group = ANY(
                COALESCE(
                    p_isco_major_groups,
                    ARRAY['1','2','3','4','5']::text[]
                )
           )

        GROUP BY
            o.occupation_uri,
            o.preferred_label,
            o.isco_group_code,
            o.isco_major_group
    ),
    metrics AS (
        SELECT
            scored.*,
            100.0 * matched_essential /
                NULLIF(total_essential, 0) AS essential_pct,
            100.0 * weighted_matched /
                NULLIF(weighted_total, 0) AS weighted_pct
        FROM scored
    )
    SELECT
        m.occupation_uri,
        m.preferred_label,
        m.isco_group_code,
        m.isco_major_group,
        m.matched_essential,
        m.total_essential,
        ROUND(m.essential_pct, 1),
        m.matched_optional,
        m.total_optional,
        ROUND(m.weighted_pct, 1)

    FROM metrics m

    WHERE m.matched_essential >=
        GREATEST(COALESCE(p_min_matched_essential, 2), 0)
       OR m.essential_pct > 15.0

    ORDER BY
        m.weighted_pct DESC,
        m.essential_pct DESC,
        m.preferred_label ASC;
$function$;
