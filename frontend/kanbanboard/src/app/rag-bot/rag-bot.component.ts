import { CommonModule } from '@angular/common';
import { Component, DestroyRef, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { RagBotService, type RagHistoryMessage, type RagSource, type RagStreamEvent } from './rag-bot.service';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: RagSource[];
}

@Component({
  selector: 'app-rag-bot',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './rag-bot.component.html',
  styleUrl: './rag-bot.component.css'
})
export class RagBotComponent {
  private readonly ragBotService = inject(RagBotService);
  private readonly destroyRef = inject(DestroyRef);

  @ViewChild('messageList') private messageList?: ElementRef<HTMLElement>;

  protected readonly messages = signal<ChatMessage[]>([]);
  protected readonly question = signal('');
  protected readonly isLoading = signal(false);
  protected readonly errorMessage = signal('');

  protected readonly suggestions = [
    'Who is assigned to a ticket?',
    'Show the details of a ticket.',
    'What is the current status of a ticket?',
    'Find tickets related to a particular project.'
  ];

  protected useSuggestion(suggestion: string): void {
    this.question.set(suggestion);
  }

  protected submitQuestion(): void {
    const question = this.question().trim();
    if (!question || this.isLoading()) {
      return;
    }

    const history: RagHistoryMessage[] = this.messages()
      .filter((message) => message.content.trim())
      .map((message) => ({ role: message.role, content: message.content }));
    this.messages.update((messages) => [...messages, { role: 'user', content: question }]);
    const assistantIndex = this.messages().length;
    this.messages.update((messages) => [...messages, { role: 'assistant', content: '' }]);
    this.question.set('');
    this.errorMessage.set('');
    this.isLoading.set(true);
    this.scrollToLatest();

    this.ragBotService.streamQuestion(question, history).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (event: RagStreamEvent) => {
        if (event.type === 'chunk') {
          this.updateAssistantMessage(assistantIndex, (message) => ({
            ...message,
            content: message.content + event.text
          }));
        } else if (event.type === 'complete') {
          this.updateAssistantMessage(assistantIndex, (message) => ({
            ...message,
            content: event.answer || "I don't know based on the provided ticket context.",
            sources: event.sources
          }));
          this.isLoading.set(false);
        }
        this.scrollToLatest();
      },
      error: (error: Error) => {
        this.isLoading.set(false);
        this.errorMessage.set(error.message || 'The assistant could not be reached. Check that the backend is running and try again.');
        this.scrollToLatest();
      }
    });
  }

  protected onComposerKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.submitQuestion();
    }
  }

  private scrollToLatest(): void {
    setTimeout(() => {
      const element = this.messageList?.nativeElement;
      if (element) {
        element.scrollTop = element.scrollHeight;
      }
    });
  }

  private updateAssistantMessage(index: number, update: (message: ChatMessage) => ChatMessage): void {
    const message = this.messages()[index];
    if (!message) {
      return;
    }
    this.messages.update((messages) => messages.map((item, itemIndex) => itemIndex === index ? update(message) : item));
  }
}
