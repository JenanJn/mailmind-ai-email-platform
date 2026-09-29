import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { Email, Reply } from '../types'
import EmailDetail from './EmailDetail'
import ReplyEditor from '../components/reply/ReplyEditor'

const mockGet = vi.hoisted(() => vi.fn())
const mockGenerate = vi.hoisted(() => vi.fn())

vi.mock('../api/emails', () => ({
  emailsApi: {
    get: mockGet,
    analyze: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('../api/replies', () => ({
  repliesApi: {
    generate: mockGenerate,
    regenerate: vi.fn(),
    modify: vi.fn(),
    edit: vi.fn(),
    history: vi.fn(),
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

const generatedReply: Reply = {
  id: 'reply-1',
  current_content: 'Thank you. I will confirm the meeting time.',
  tone: 'formal',
  status: 'draft',
  is_user_edited: false,
  generated_at: '2026-09-28T10:00:01Z',
  updated_at: '2026-09-28T10:00:01Z',
}

const analyzedEmail: Email = {
  ...pendingEmail,
  is_analyzed: true,
  reply: generatedReply,
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
    const generateButton = screen.getByRole('button', { name: 'Generate Smart Reply' })
    expect((generateButton as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(generateButton)
    expect(mockGenerate).not.toHaveBeenCalled()

    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })

    expect(mockGet).toHaveBeenCalledTimes(2)
    expect(screen.getAllByText('Work / Professional').length).toBeGreaterThan(0)
    expect(screen.getByText(generatedReply.current_content)).toBeTruthy()
    expect(screen.queryByText('Analyzing email...')).toBeNull()
  })

  it('clears a generation error when a reply arrives through props', async () => {
    mockGenerate.mockRejectedValueOnce(new Error('generation failed'))
    const onReplyUpdate = vi.fn()
    const editor = render(
      <ReplyEditor emailId="email-1" isAnalyzed={true} reply={null} onReplyUpdate={onReplyUpdate} />,
    )

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Generate Smart Reply' }))
      await Promise.resolve()
    })
    expect(screen.getByText('Failed to generate reply. Please try again.')).toBeTruthy()

    editor.rerender(
      <ReplyEditor emailId="email-1" isAnalyzed={true} reply={generatedReply} onReplyUpdate={onReplyUpdate} />,
    )

    expect(screen.getByText(generatedReply.current_content)).toBeTruthy()
    expect(screen.queryByText('Failed to generate reply. Please try again.')).toBeNull()
  })

  it('shows a timeout state after two minutes', async () => {
    mockGet.mockResolvedValue(pendingEmail)
    renderEmailDetail()

    await act(async () => { await Promise.resolve() })
    await act(async () => { await vi.advanceTimersByTimeAsync(120000) })

    expect(screen.getByText('Analysis is taking longer than expected.')).toBeTruthy()
  })
})