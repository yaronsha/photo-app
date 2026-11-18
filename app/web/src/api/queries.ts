import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchMe, fetchPeople, fetchSearch, fetchPhotoInfo, setPhotoHidden } from './client';
import type { SearchParams, SearchResult } from './types';

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

/** Current user's identity + admin flag. Admin only gates UI; the server
 *  re-checks on every hide/unhide call. */
export function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: fetchMe,
    staleTime: Infinity,
    retry: false,
  });
}

export function useSetPhotoHidden() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ photoId, hidden }: { photoId: string; hidden: boolean }) =>
      setPhotoHidden(photoId, hidden),
    onSuccess: (_data, { photoId }) => {
      queryClient.invalidateQueries({ queryKey: ['search'] });
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
