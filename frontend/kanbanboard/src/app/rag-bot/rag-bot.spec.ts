import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RagBot } from './rag-bot';

describe('RagBot', () => {
  let component: RagBot;
  let fixture: ComponentFixture<RagBot>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RagBot],
    }).compileComponents();

    fixture = TestBed.createComponent(RagBot);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
