import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { Email } from '../types'
import EmailDetail from './EmailDetail'

const mockGet = vi.hoisted(() => vi.fn())

vi.mock('../api/emails', () => ({
  emailsApi: {
    get: mockGet,
    analyze: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('../components/analysis/AIInsightPanel', () => ({
  default: ({ analysis }: { analysis: { category_name: string | null } }) => (
    <div>{analysis.category_name}</div>
  ),
}))

const pendingEmail: Email = {
  id: 'email-1',
  sender_name: 'Sender',
  sender_email: 'sender@example.com',
  subject: 'Pending message',
  body: 'Email body',
  received_at: '2026-09-28T10:00:00Z',
  is_analyzed: false,
  created_at: '2026-09-28T10:00:00Z',
  analysis: null,
  entities: null,
  reply: null,
}

const analyzedEmail: Email = {
  ...pendingEmail,
  is_analyzed: true,
  analysis: {
    id: 'analysis-1',
    category_name: 'Work / Professional',
    category_confidence: 0.9,
    intent: 'Meeting Request',
    priority_level: 'medium',
    priority_score: 50,
    urgency_level: 'normal',
    sentiment: 'neutral',
    sentiment_score: 0,
    action_required: false,
    deadline_text: null,
    key_points: [],
    ai_explanation: [],
    priority_factors: '{}',
    analyzed_at: '2026-09-28T10:00:01Z',
  },
  entities: [],
  reply: null,
}

function renderEmailDetail() {
  render(
    <MemoryRouter initialEntries={['/inbox/email-1']}>
      <Routes>
        <Route path="/inbox/:id" element={<EmailDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('EmailDetail background analysis', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-28T10:00:00Z'))
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('polls until the email is analyzed', async () => {
    mockGet.mockResolvedValueOnce(pendingEmail).mockResolvedValueOnce(analyzedEmail)
    renderEmailDetail()

    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('Analyzing email...')).toBeTruthy()

    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })

    expect(mockGet).toHaveBeenCalledTimes(2)
    expect(screen.getAllByText('Work / Professional').length).toBeGreaterThan(0)
    expect(screen.queryByText('Analyzing email...')).toBeNull()
  })

  it('shows a timeout state after two minutes', async () => {
    mockGet.mockResolvedValue(pendingEmail)
    renderEmailDetail()

    await act(async () => { await Promise.resolve() })
    await act(async () => { await vi.advanceTimersByTimeAsync(120000) })

    expect(screen.getByText('Analysis is taking longer than expected.')).toBeTruthy()
  })
})