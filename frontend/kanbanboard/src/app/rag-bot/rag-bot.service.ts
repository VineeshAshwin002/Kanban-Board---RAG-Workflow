import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export interface RagSource {
  project_id: string | number;
  ticket_id: string | number;
  title?: string;
  view_url?: string;
}

export interface RagResponse {
  success: boolean;
  answer: string;
  sources: RagSource[];
}

export interface RagHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export type RagStreamEvent =
  | { type: 'start'; request_id: string }
  | { type: 'chunk'; text: string }
  | { type: 'complete'; answer: string; sources: RagSource[] }
  | { type: 'error'; message: string };

@Injectable({ providedIn: 'root' })
export class RagBotService {
  private readonly apiBaseUrl = 'http://localhost:5000';

  streamQuestion(message: string, history: RagHistoryMessage[] = []): Observable<RagStreamEvent> {
    return new Observable<RagStreamEvent>((observer) => {
      const controller = new AbortController();
      let cancelled = false;
      let finished = false;

      const dispatch = (rawEvent: string): void => {
        let eventType = 'message';
        const dataLines: string[] = [];
        for (const line of rawEvent.split(/\r?\n/)) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).trimStart());
          }
        }
        if (!dataLines.length || finished) {
          return;
        }
        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(dataLines.join('\n')) as Record<string, unknown>;
        } catch {
          observer.error(new Error('The assistant returned malformed streaming data.'));
          return;
        }

        if (eventType === 'start') {
          observer.next({ type: 'start', request_id: String(payload['request_id'] ?? '') });
        } else if (eventType === 'chunk') {
          observer.next({ type: 'chunk', text: String(payload['text'] ?? '') });
        } else if (eventType === 'complete') {
          finished = true;
          observer.next({
            type: 'complete',
            answer: String(payload['answer'] ?? ''),
            sources: Array.isArray(payload['sources']) ? payload['sources'] as RagSource[] : []
          });
          observer.complete();
        } else if (eventType === 'error') {
          finished = true;
          observer.error(new Error(String(payload['message'] ?? 'Unable to generate a response.')));
        }
      };

      const consume = async (): Promise<void> => {
        try {
          const response = await fetch(`${this.apiBaseUrl}/api/rag/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
            body: JSON.stringify({ message, history: history.slice(-6) }),
            signal: controller.signal
          });
          if (!response.ok) {
            throw new Error(`The assistant request failed with status ${response.status}.`);
          }
          if (!response.body) {
            throw new Error('The assistant did not return a streaming response.');
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          while (!cancelled) {
            const result = await reader.read();
            if (result.done) {
              buffer += decoder.decode();
              break;
            }
            buffer += decoder.decode(result.value, { stream: true });
            let boundary = buffer.search(/\r?\n\r?\n/);
            while (boundary >= 0) {
              const separator = buffer.slice(boundary).match(/^\r?\n\r?\n/)?.[0] ?? '\n\n';
              dispatch(buffer.slice(0, boundary));
              buffer = buffer.slice(boundary + separator.length);
              boundary = buffer.search(/\r?\n\r?\n/);
            }
          }
          if (buffer.trim() && !finished) {
            dispatch(buffer);
          }
          if (!finished && !cancelled) {
            observer.error(new Error('The assistant stream ended before completion.'));
          }
        } catch (error) {
          if (!cancelled) {
            observer.error(error instanceof Error ? error : new Error('The assistant request failed.'));
          }
        }
      };

      void consume();
      return () => {
        cancelled = true;
        controller.abort();
      };
    });
  }
}
