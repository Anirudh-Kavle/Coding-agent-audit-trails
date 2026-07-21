import type { FlightEvent, Session } from "../types";
import { mockEvents, mockSessions, generateMockEvent } from "./mockData";
import { filterEvents, sessionTitleMap } from "./search";
import * as api from "./api";

// Single adapter behind the whole UI. Live (:7878 via the vite proxy) by
// default; VITE_USE_MOCK=true npm run dev brings back the mock demo.
const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

// Interval between simulated live events (ms). Demo-friendly cadence.
const MOCK_STREAM_MS = 4000;

export interface DataSource {
  getSessions(): Promise<Session[]>;
  getEvents(sessionId?: string): Promise<FlightEvent[]>;
  search(query: string): Promise<FlightEvent[]>;
  subscribe(onEvent: (e: FlightEvent) => void): () => void;
  getRecordingPaused(): Promise<boolean>;
  setRecordingPaused(paused: boolean): Promise<boolean>;
}

// Mock mode has no server to persist against — an in-memory flag is enough
// to make the toggle behave believably within a single demo session.
let mockPaused = false;

const mockSource: DataSource = {
  async getSessions() {
    return mockSessions;
  },
  async getEvents(sessionId) {
    return sessionId
      ? mockEvents.filter((e) => e.session_id === sessionId)
      : mockEvents;
  },
  async search(query) {
    return filterEvents(mockEvents, query, sessionTitleMap(mockSessions));
  },
  subscribe(onEvent) {
    const timer = setInterval(() => {
      if (mockPaused) return;
      const e = generateMockEvent();
      mockEvents.push(e);
      onEvent(e);
    }, MOCK_STREAM_MS);
    return () => clearInterval(timer);
  },
  async getRecordingPaused() {
    return mockPaused;
  },
  async setRecordingPaused(paused) {
    mockPaused = paused;
    return mockPaused;
  },
};

// The backend defaults /api/sessions/{id}/events to limit=500 as a sanity
// cap, not a UI page size — asking for it explicitly here means the app's
// actual history window is a deliberate choice, not an accident of whatever
// the backend's default happens to be.
// ponytail: still a hard cap, not real pagination — raise further (or add a
// "load more") if a single local install's history ever grows past this.
const EVENT_HISTORY_LIMIT = "5000";

const liveSource: DataSource = {
  getSessions: api.getSessions,
  getEvents: (sessionId) => api.getEvents(sessionId, { limit: EVENT_HISTORY_LIMIT }),
  search: (query) => api.search(query),
  subscribe: (onEvent) => api.streamEvents(onEvent),
  getRecordingPaused: api.getRecordingPaused,
  setRecordingPaused: api.setRecordingPaused,
};

export const dataSource: DataSource = USE_MOCK ? mockSource : liveSource;
