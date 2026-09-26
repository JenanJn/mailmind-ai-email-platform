import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PlusCircle, Sparkles, ChevronDown, ChevronUp, CheckCircle } from 'lucide-react'
import { emailsApi } from '../api/emails'
import { useAuth } from '../hooks/useAuth'
import { SAMPLE_EMAILS } from '../data/sampleEmails'

export default function AddEmail() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [mode, setMode] = useState<'manual' | 'sample'>('manual')
  const [expandedSample, setExpandedSample] = useState<number | null>(null)

  // Form state
  const [senderName, setSenderName] = useState('')
  const [senderEmail, setSenderEmail] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fillSample = (idx: number) => {
    const s = SAMPLE_EMAILS[idx]
    setSenderName(s.data.sender_name)
    setSenderEmail(s.data.sender_email)
    setSubject(s.data.subject)
    setBody(s.data.body)
    setMode('manual')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!body.trim()) { setError('Email body is required.'); return }
    if (!senderEmail.trim()) { setError('Sender email is required.'); return }
    if (!user?.email) { setError('Could not determine the authenticated user email.'); return }
    setLoading(true)
    setError(null)
    try {
      const email = await emailsApi.incoming({
        sender: senderEmail.trim(),
        recipient: user.email,
        subject: subject || undefined,
        body,
        received_at: new Date().toISOString(),
      })
      navigate(`/inbox/${email.id}`)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      const message = !err?.response
        ? 'The API is unavailable. Start the backend and try again.'
        : err.response.status >= 500
        ? 'The server could not analyze this email. Please try again.'
        : null
      setError(
        Array.isArray(detail)
          ? detail.map((d: any) => d.msg).join(', ')
          : detail ?? message ?? 'Failed to add email. Please try again.',
      )
    } finally {
      setLoading(false)
    }
  }

  const clearForm = () => {
    setSenderName(''); setSenderEmail(''); setSubject(''); setBody(''); setError(null)
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <PlusCircle className="w-6 h-6 text-blue-400" />
          Add Email
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Enter an email to classify, prioritize, and generate a smart reply.
        </p>
      </div>

      {/* Mode tabs */}
      <div className="flex rounded-lg bg-slate-800 p-1 mb-6 w-fit">
        {(['manual', 'sample'] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all capitalize ${
              mode === m ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            {m === 'manual' ? 'Enter Manually' : 'Choose Sample'}
          </button>
        ))}
      </div>

      {/* Sample picker */}
      {mode === 'sample' && (
        <div className="space-y-2 mb-6 animate-fade-in">
          <p className="text-xs text-slate-500 mb-3">
            Click a sample to preview it, then click "Use this sample" to fill the form.
          </p>
          {SAMPLE_EMAILS.map((s, i) => (
            <div key={i} className="card border border-slate-700">
              <button
                onClick={() => setExpandedSample(expandedSample === i ? null : i)}
                className="w-full flex items-center justify-between text-left"
              >
                <div className="flex items-center gap-3">
                  <Sparkles className="w-4 h-4 text-blue-400 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-white">{s.label}</p>
                    <p className="text-xs text-slate-500">{s.category} · {s.data.sender_name}</p>
                  </div>
                </div>
                {expandedSample === i ? (
                  <ChevronUp className="w-4 h-4 text-slate-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-slate-400" />
                )}
              </button>

              {expandedSample === i && (
                <div className="mt-3 pt-3 border-t border-slate-700 animate-fade-in">
                  <p className="text-xs text-slate-400 font-medium mb-1">Subject: {s.data.subject}</p>
                  <pre className="text-xs text-slate-500 whitespace-pre-wrap font-sans leading-relaxed line-clamp-6">
                    {s.data.body}
                  </pre>
                  <button
                    onClick={() => fillSample(i)}
                    className="btn-primary text-xs mt-3 flex items-center gap-1.5"
                  >
                    <CheckCircle className="w-3.5 h-3.5" />
                    Use this sample
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Manual form */}
      {mode === 'manual' && (
        <form onSubmit={handleSubmit} className="card space-y-4 animate-fade-in">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Sender Name</label>
              <input
                type="text"
                value={senderName}
                onChange={(e) => setSenderName(e.target.value)}
                placeholder="e.g. HR Team"
                className="input"
              />
            </div>
            <div>
              <label className="label">Sender Email</label>
              <input
                type="email"
                value={senderEmail}
                onChange={(e) => setSenderEmail(e.target.value)}
                placeholder="e.g. hr@company.com"
                required
                className="input"
              />
            </div>
          </div>

          <div>
            <label className="label">Subject</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Email subject line"
              className="input"
            />
          </div>

          <div>
            <label className="label">Email Body <span className="text-red-400">*</span></label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Paste or type the email content here..."
              rows={12}
              required
              className="input resize-none font-mono text-sm leading-relaxed"
            />
          </div>

          {error && (
            <div className="bg-red-500/15 border border-red-500/30 rounded-lg px-3 py-2 text-sm text-red-300">
              {error}
            </div>
          )}

          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={loading || !body.trim()}
              className="btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Analyzing with AI...
                </span>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  Analyze with AI
                </>
              )}
            </button>
            {(body || subject || senderName) && (
              <button type="button" onClick={clearForm} className="btn-ghost text-sm">
                Clear
              </button>
            )}
          </div>

          <p className="text-xs text-slate-500">
            The AI will classify the category, detect intent, score priority, extract entities, and generate a smart reply automatically.
          </p>
        </form>
      )}
    </div>
  )
}

import type React from 'react'
