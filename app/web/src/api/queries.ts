import {
  useQuery,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from '@tanstack/react-query';
import { fetchMe, fetchPeople, fetchSearch, fetchPhotoInfo, setPhotoHidden } from './client';
import type { SearchParams, SearchResponse, SearchResult } from './types';

const LIMIT = 50;

export function usePeople() {
  return useQuery({
    queryKey: ['people'],
    queryFn: fetchPeople,
    staleTime: Infinity,
    retry: false,
  });
}

export interface SearchFilters {
  q: string;
  dateFrom: string;
  dateTo: string;
  personIds: string[];
  peopleMode: 'any' | 'all';
  /** Admin "Hidden" view: only hidden photos, works with no other filter. */
  hiddenOnly?: boolean;
}

export function hasAnyFilter(filters: SearchFilters): boolean {
  return !!(
    filters.q ||
    filters.dateFrom ||
    filters.dateTo ||
    filters.personIds.length ||
    filters.hiddenOnly
  );
}

export function useSearchInfinite(filters: SearchFilters) {
  const enabled = hasAnyFilter(filters);
  return useInfiniteQuery({
    queryKey: ['search', filters],
    queryFn: ({ pageParam = 0 }) => {
      const params: SearchParams = {
        limit: LIMIT,
        offset: pageParam as number,
      };
      if (filters.q) params.q = filters.q;
      if (filters.dateFrom) params.date_from = filters.dateFrom;
      if (filters.dateTo) params.date_to = filters.dateTo;
      if (filters.personIds.length) {
        params.person_id = filters.personIds;
        params.people_mode = filters.peopleMode;
      }
      if (filters.hiddenOnly) params.hidden = 'only';
      return fetchSearch(params);
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage.has_more) return undefined;
      return allPages.reduce((sum, page) => sum + page.results.length, 0);
    },
    enabled,
    staleTime: 30_000,
  });
}

export function flattenPages(
  pages: Array<{ results: SearchResult[] }> | undefined,
): SearchResult[] {
  if (!pages) return [];
  return pages.flatMap(p => p.results);
}

/** Current user's identity + admin flag (also the allowlist probe in App).
 *  Keyed by the signed-in user so a sign-out/sign-in as someone else never
 *  reuses the previous user's admin flag. Admin only gates UI; the server
 *  re-checks on every hide/unhide call. */
export function useMe(userKey: string | null, enabled = true) {
  return useQuery({
    queryKey: ['me', userKey],
    queryFn: fetchMe,
    staleTime: Infinity,
    retry: false,
    enabled,
  });
}

function isHiddenView(queryKey: readonly unknown[]): boolean {
  const filters = queryKey[1] as SearchFilters | undefined;
  return !!filters?.hiddenOnly;
}

export function useSetPhotoHidden() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ photoId, hidden }: { photoId: string; hidden: boolean }) =>
      setPhotoHidden(photoId, hidden),
    onSuccess: (_data, { photoId, hidden }) => {
      // Lists the photo just left (normal views on hide, the Hidden view on
      // unhide): drop it from the cached pages instead of refetching every
      // loaded page.
      const leaving = (q: { queryKey: readonly unknown[] }) =>
        q.queryKey[0] === 'search' && isHiddenView(q.queryKey) !== hidden;
      queryClient.setQueriesData<InfiniteData<SearchResponse>>(
        { predicate: leaving },
        data =>
          data && {
            ...data,
            pages: data.pages.map(p => ({
              ...p,
              results: p.results.filter(r => r.id !== photoId),
            })),
          },
      );
      // Lists it just joined: refetch only if on screen (e.g. Undo),
      // otherwise mark stale for next time.
      queryClient.invalidateQueries({
        predicate: q => q.queryKey[0] === 'search' && !leaving(q),
      });
      queryClient.invalidateQueries({ queryKey: ['photoInfo', photoId] });
    },
  });
}

export function usePhotoInfo(photoId: string | null) {
  return useQuery({
    queryKey: ['photoInfo', photoId],
    queryFn: () => fetchPhotoInfo(photoId!),
    enabled: photoId != null,
    staleTime: 60_000,
  });
}
