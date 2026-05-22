import type { Person, SearchParams, SearchResponse, PhotoInfo } from './types';
import { supabase } from '../lib/supabase';

const BASE = '';

async function authHeaders(): Promise<Headers> {
  const headers = new Headers();
  if (!supabase) return headers;
  const { data } = await supabase.auth.getSession();
  if (data.session) {
    headers.set('Authorization', `Bearer ${data.session.access_token}`);
  }
  return headers;
}

async function apiFetch<T>(path: string): Promise<T> {
  const headers = await authHeaders();
  const resp = await fetch(`${BASE}${path}`, { headers });
  if (!resp.ok) {
    throw new Error(`API error ${resp.status}: ${resp.url}`);
  }
  return resp.json() as Promise<T>;
}

export function fetchPeople(): Promise<Person[]> {
  return apiFetch<Person[]>('/people');
}

export function fetchSearch(params: SearchParams): Promise<SearchResponse> {
  const q = new URLSearchParams();
  if (params.q) q.set('q', params.q);
  if (params.limit != null) q.set('limit', String(params.limit));
  if (params.offset != null) q.set('offset', String(params.offset));
  if (params.date_from) q.set('date_from', params.date_from);
  if (params.date_to) q.set('date_to', params.date_to);
  if (params.person_id?.length) {
    params.person_id.forEach(id => q.append('person_id', id));
  }
  if (params.people_mode && params.people_mode !== 'any') {
    q.set('people_mode', params.people_mode);
  }
  if (params.include_docs) q.set('include_docs', 'true');
  return apiFetch<SearchResponse>(`/search?${q.toString()}`);
}

export function fetchPhotoInfo(photoId: string): Promise<PhotoInfo> {
  return apiFetch<PhotoInfo>(`/photo/${encodeURIComponent(photoId)}/info`);
}
