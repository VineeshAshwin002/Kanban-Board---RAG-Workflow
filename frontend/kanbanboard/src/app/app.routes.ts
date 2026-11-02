import { Routes } from '@angular/router';
import { RagBotComponent } from './rag-bot/rag-bot.component';

export const routes: Routes = [
	{ path: 'rag-bot', component: RagBotComponent },
	{ path: '**', redirectTo: '' }
];
