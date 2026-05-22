-- Add dashboard eligibility fields to the channel discovery view.

create or replace view channel_discovery as
select
    c.id,
    c.platform,
    c.channel_url,
    c.name,
    c.description,
    c.subscriber_count,
    c.avg_views,
    c.avg_comments,
    c.comment_tier,
    c.posts_per_week,
    c.last_active_date,
    c.contact_info,
    c.niche_tags,
    c.video_titles,
    c.is_active,
    c.is_55_plus,
    c.gate0_status,
    c.gate0_checked_at,
    c.secondary_urls,
    c.created_at,
    c.updated_at,
    vs.id as velocity_id,
    vs.computed_at as velocity_computed_at,
    vs.view_velocity_30d,
    vs.view_velocity_90d,
    vs.comment_velocity_30d,
    vs.comment_velocity_90d,
    gr.id as gate0_result_id,
    gr.checked_at as gate0_result_checked_at,
    gr.search_query as gate0_search_query,
    gr.result_status as gate0_result_status,
    gr.flagged_brand as gate0_flagged_brand,
    gr.source_url as gate0_source_url,
    c.has_been_scraped,
    c.discovery_status,
    c.last_scrape_error,
    (
        c.subscriber_count is not null
        and c.avg_views is not null
        and c.avg_comments is not null
        and c.last_active_date is not null
    ) as dashboard_metrics_complete,
    (
        (
            c.platform = 'rumble'
            and (
                c.channel_url ~ '^https://rumble\.com/(c|user)/[A-Za-z0-9][A-Za-z0-9_-]{1,127}/?$'
                or (
                    c.channel_url ~ '^https://rumble\.com/[A-Za-z0-9][A-Za-z0-9_-]{1,127}/?$'
                    and c.channel_url !~ '^https://rumble\.com/(about|account|blog|category|embed|login|premium|register|search|settings|static|user|videos|v[A-Za-z0-9_-]+)/?$'
                )
            )
        )
        or (
            c.platform = 'bitchute'
            and c.channel_url ~ '^https://bitchute\.com/channel/[A-Za-z0-9][A-Za-z0-9_-]{1,127}/?$'
        )
    ) as dashboard_url_valid,
    (
        c.is_active = true
        and c.has_been_scraped = true
        and c.discovery_status = 'scraped'
        and c.subscriber_count is not null
        and c.avg_views is not null
        and c.avg_comments is not null
        and c.last_active_date is not null
        and (
            (
                c.platform = 'rumble'
                and (
                    c.channel_url ~ '^https://rumble\.com/(c|user)/[A-Za-z0-9][A-Za-z0-9_-]{1,127}/?$'
                    or (
                        c.channel_url ~ '^https://rumble\.com/[A-Za-z0-9][A-Za-z0-9_-]{1,127}/?$'
                        and c.channel_url !~ '^https://rumble\.com/(about|account|blog|category|embed|login|premium|register|search|settings|static|user|videos|v[A-Za-z0-9_-]+)/?$'
                    )
                )
            )
            or (
                c.platform = 'bitchute'
                and c.channel_url ~ '^https://bitchute\.com/channel/[A-Za-z0-9][A-Za-z0-9_-]{1,127}/?$'
            )
        )
    ) as dashboard_eligible
from channels c
left join velocity_scores vs on vs.channel_id = c.id
left join lateral (
    select *
    from gate0_results
    where gate0_results.channel_id = c.id
    order by checked_at desc
    limit 1
) gr on true;
