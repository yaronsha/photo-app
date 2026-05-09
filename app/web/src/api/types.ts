export interface Person {
  id: string;
  name: string;
}

export interface SearchParams {
  q?: string;
  limit?: number;
  offset?: number;
  date_from?: string;  // 'YYYY-MM-DD'
  date_to?: string;    // 'YYYY-MM-DD'
  person_id?: string[];
  people_mode?: 'any' | 'all';
  include_docs?: boolean;
}

export interface SearchResult {
  id: string;
  caption: string | null;
  taken_at: string | null;
  thumb_url: string;
  score: number;
  location_name: string | null;
  tags: string[];
  people: Person[];
  activities: string[];
  content_type: string | null;
  subject_type: string | null;
  setting_type: string | null;
  sharpness: string | null;
  face_clarity_score: number | null;
  primary_focus: string | null;
  indoor_outdoor: string | null;
}

export interface SearchResponse {
  results: SearchResult[];
  has_more: boolean;
}

export interface PhotoInfo {
  id: string;
  caption: string | null;
  taken_at: string | null;
  location_name: string | null;
  description: string | null;
  tags: string[];
  people: Person[];
  activities: string[];
  content_type: string | null;
  subject_type: string | null;
  primary_focus: string | null;
  indoor_outdoor: string | null;
  setting_type: string | null;
  sharpness: string | null;
  face_clarity_score: number | null;
}
