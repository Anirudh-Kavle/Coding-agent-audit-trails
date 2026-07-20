import type { FlightEvent, Session, SummaryResponse } from "../types";
import { mockEvents, mockSessions, generateMockEvent } from "./mockData";
import { filterEvents } from "./search";
import * as api from "./api";

// Single adapter behind the whole UI. Live (:7878 via the vite proxy) by
// default; VITE_USE_MOCK=true npm run dev brings back the mock demo.
const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

// Interval between simulated live events (ms). Demo-friendly cadence.
const MOCK_STREAM_MS = 4000;

export interface DataSource {
  getSessions(): Promise<Session[]>;
  getEvents(sessionId?: string): Promise<FlightEvent[]>;
  getEvent(id: number): Promise<FlightEvent | undefined>;
  search(query: string): Promise<FlightEvent[]>;
  getSummary(sessionId: string): Promise<SummaryResponse>;
  generateSummary(sessionId: string): Promise<SummaryResponse>;
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
  async getEvent(id) {
    return mockEvents.find((e) => e.id === id);
  },
  async search(query) {
    return filterEvents(mockEvents, query);
  },
  // No local model in mock mode — the summary panel simply hides itself.
  async getSummary() {
    return { summary: null, available: false };
  },
  async generateSummary() {
    return { summary: null, available: false };
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

const liveSource: DataSource = {
  getSessions: api.getSessions,
  getEvents: (sessionId) => api.getEvents(sessionId),
  getEvent: (id) => api.getEvent(id),
  search: (query) => api.search(query),
  getSummary: (sessionId) => api.getSummary(sessionId),
  generateSummary: (sessionId) => api.generateSummary(sessionId),
  subscribe: (onEvent) => api.streamEvents(onEvent),
  getRecordingPaused: api.getRecordingPaused,
  setRecordingPaused: api.setRecordingPaused,
};

export const dataSource: DataSource = USE_MOCK ? mockSource : liveSource;
