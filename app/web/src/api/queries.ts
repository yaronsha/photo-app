import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import { fetchPeople, fetchSearch, fetchPhotoInfo } from './client';
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
}

export function hasAnyFilter(filters: SearchFilters): boolean {
  return !!(
    filters.q ||
    filters.dateFrom ||
    filters.dateTo ||
    filters.personIds.length
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

export function usePhotoInfo(photoId: string | null) {
  return useQuery({
    queryKey: ['photoInfo', photoId],
    queryFn: () => fetchPhotoInfo(photoId!),
    enabled: photoId != null,
    staleTime: 60_000,
  });
}
