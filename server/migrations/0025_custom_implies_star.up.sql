-- 0025_custom_implies_star — 自选(custom)统一为★关注(starred):自选即关注,避免「自选/关注/推荐」三层排序。
-- 追平存量:把所有已存在的自选股补为 starred=true(幂等)。新加自选由 watchCustom 同时设 starred。
UPDATE watchlist SET starred = true WHERE custom = true AND starred = false;
