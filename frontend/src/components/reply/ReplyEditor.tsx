import { useState, useEffect } from 'react'
import {
  RefreshCw,
  Edit3,
  Check,
  X,
  History,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Send,
  Copy,
} from 'lucide-react'
import clsx from 'clsx'
import type { Reply, ReplyVersion } from '../../types'
import { repliesApi } from '../../api/replies'
import { formatDateTime } from '../../utils/dateFormat'

interface Props {
  emailId: string
  reply: Reply | null
  onReplyUpdate: (reply: Reply) => void
}

type StyleOption = 'shorter' | 'formal' | 'friendly' | 'longer'

const STYLE_OPTIONS: { value: StyleOption; label: string; desc: string }[] = [
  { value: 'shorter',  label: 'Shorter',      desc: 'Condense to 2–3 lines' },
  { value: 'formal',   label: 'More Formal',  desc: 'Professional language' },
  { value: 'friendly', label: 'Friendlier',   desc: 'Warmer tone' },
  { value: 'longer',   label: 'More Detail',  desc: 'Expand the reply' },
]

export default function ReplyEditor({ emailId, reply, onReplyUpdate }: Props) {
  const [content, setContent] = useState(reply?.current_content ?? '')
  const [isEditing, setIsEditing] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [loadingAction, setLoadingAction] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [history, setHistory] = useState<ReplyVersion[]>(reply?.versions ?? [])
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    setContent(reply?.current_content ?? '')
    setHistory(reply?.versions ?? [])
  }, [reply])

  const handleGenerate = async () => {
    setIsLoading(true)
    setLoadingAction('generate')
    setError(null)
    try {
      const updated = await repliesApi.generate(emailId)
      onReplyUpdate(updated)
    } catch {
      setError('Failed to generate reply. Please try again.')
    } finally {
      setIsLoading(false)
      setLoadingAction(null)
    }
  }

  const handleRegenerate = async () => {
    setIsLoading(true)
    setLoadingAction('regenerate')
    setError(null)
    try {
      const updated = await repliesApi.regenerate(emailId)
      onReplyUpdate(updated)
    } catch {
      setError('Failed to regenerate. Please try again.')
    } finally {
      setIsLoading(false)
      setLoadingAction(null)
    }
  }

  const handleModify = async (style: StyleOption) => {
    setIsLoading(true)
    setLoadingAction(style)
    setError(null)
    try {
      const updated = await repliesApi.modify(emailId, style)
      onReplyUpdate(updated)
    } catch {
      setError('Failed to modify reply. Please try again.')
    } finally {
      setIsLoading(false)
      setLoadingAction(null)
    }
  }

  const handleSaveEdit = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const updated = await repliesApi.edit(emailId, content)
      onReplyUpdate(updated)
      setIsEditing(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      setError('Failed to save. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCopy = async () => {
    if (!reply?.current_content) return
    try {
      await navigator.clipboard.writeText(reply.current_content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setError('Could not copy the reply. Please select and copy it manually.')
    }
  }

  const handleCancelEdit = () => {
    setContent(reply?.current_content ?? '')
    setIsEditing(false)
  }

  const loadHistory = async () => {
    if (!showHistory) {
      try {
        const versions = await repliesApi.history(emailId)
        setHistory(versions)
      } catch {
        // silently fail
      }
    }
    setShowHistory((v) => !v)
  }

  // No reply yet
  if (!reply) {
    return (
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-bold text-white">AI Generated Reply</span>
        </div>
        {error && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}
        <div className="text-center py-8">
          <div className="w-12 h-12 rounded-full bg-blue-600/20 flex items-center justify-center mx-auto mb-3">
            <Sparkles className="w-6 h-6 text-blue-400" />
          </div>
          <p className="text-sm text-slate-400 mb-4">
            {error ? 'Reply generation failed. Try again when you are ready.' : 'Generate a context-aware reply tailored to this email\'s category and intent.'}
          </p>
          <button
            onClick={handleGenerate}
            disabled={isLoading}
            className="btn-primary flex items-center gap-2 mx-auto"
          >
            {isLoading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            {error ? 'Retry Generation' : 'Generate Smart Reply'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="card space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-bold text-white">AI Generated Reply</span>
          <span className={clsx(
            'text-xs px-2 py-0.5 rounded-full border',
            reply.is_user_edited
              ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
              : 'bg-blue-500/20 text-blue-300 border-blue-500/30',
          )}>
            {reply.is_user_edited ? 'Manually Edited' : 'AI Generated'}
          </span>
          <span className="text-xs text-slate-500">Tone: {reply.tone}</span>
          {saved && (
            <span className="text-xs text-emerald-400 flex items-center gap-1">
              <Check className="w-3 h-3" /> Saved
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleCopy}
            className="btn-ghost flex items-center gap-1 text-xs"
            title="Copy reply"
          >
            <Copy className="w-3.5 h-3.5" />
            {copied ? 'Copied' : 'Copy Reply'}
          </button>
          <button
            onClick={loadHistory}
            className="btn-ghost flex items-center gap-1 text-xs"
          >
            <History className="w-3.5 h-3.5" />
            History
            {showHistory ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/15 border border-red-500/30 rounded-lg px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Reply text area */}
      <div className="relative">
        {isEditing ? (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={10}
            className="input resize-none font-mono text-sm leading-relaxed"
            autoFocus
          />
        ) : (
          <div className="bg-slate-700/50 border border-slate-600 rounded-lg px-4 py-3 min-h-[160px]">
            <pre className="text-sm text-slate-200 whitespace-pre-wrap font-sans leading-relaxed">
              {reply.current_content}
            </pre>
          </div>
        )}

        {/* Loading overlay */}
        {isLoading && (
          <div className="absolute inset-0 bg-slate-900/70 rounded-lg flex items-center justify-center backdrop-blur-sm">
            <div className="flex items-center gap-2 text-sm text-white">
              <RefreshCw className="w-4 h-4 animate-spin text-blue-400" />
              <span>
                {loadingAction === 'regenerate' ? 'Regenerating...' :
                 loadingAction === 'generate' ? 'Generating...' :
                 `Making ${loadingAction}...`}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Action buttons */}
      {!isEditing ? (
        <div className="space-y-3">
          {/* Primary actions */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={handleRegenerate}
              disabled={isLoading}
              className="btn-secondary flex items-center gap-1.5 text-xs"
            >
              <RefreshCw className={clsx('w-3.5 h-3.5', isLoading && loadingAction === 'regenerate' && 'animate-spin')} />
              Regenerate
            </button>
            <button
              onClick={() => setIsEditing(true)}
              disabled={isLoading}
              className="btn-secondary flex items-center gap-1.5 text-xs"
            >
              <Edit3 className="w-3.5 h-3.5" />
              Edit Manually
            </button>
          </div>

          {/* Style options */}
          <div>
            <p className="text-xs text-slate-500 mb-2">Modify style:</p>
            <div className="flex flex-wrap gap-2">
              {STYLE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => handleModify(opt.value)}
                  disabled={isLoading}
                  title={opt.desc}
                  className={clsx(
                    'px-3 py-1.5 rounded-lg text-xs font-medium border transition-all',
                    loadingAction === opt.value
                      ? 'bg-blue-600 text-white border-blue-500'
                      : 'bg-slate-700/50 text-slate-300 border-slate-600 hover:border-slate-500 hover:text-white',
                  )}
                >
                  {loadingAction === opt.value ? (
                    <span className="flex items-center gap-1">
                      <RefreshCw className="w-3 h-3 animate-spin" />
                      {opt.label}
                    </span>
                  ) : opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* Edit mode buttons */
        <div className="flex items-center gap-2">
          <button
            onClick={handleSaveEdit}
            disabled={isLoading}
            className="btn-primary flex items-center gap-1.5 text-xs"
          >
            <Check className="w-3.5 h-3.5" />
            Save Edit
          </button>
          <button
            onClick={handleCancelEdit}
            disabled={isLoading}
            className="btn-secondary flex items-center gap-1.5 text-xs"
          >
            <X className="w-3.5 h-3.5" />
            Cancel
          </button>
        </div>
      )}

      {/* Version history */}
      {showHistory && history.length > 0 && (
        <div className="border-t border-slate-700 pt-4">
          <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
            Version History ({history.length})
          </p>
          <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
            {[...history].reverse().map((v) => (
              <div
                key={v.id}
                className="bg-slate-700/40 rounded-lg p-3 border border-slate-700"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-slate-400">
                    v{v.version_num} — <span className="capitalize text-slate-300">{v.change_type.replace('_', ' ')}</span>
                  </span>
                  <span className="text-xs text-slate-500">{formatDateTime(v.created_at)}</span>
                </div>
                <pre className="text-xs text-slate-400 whitespace-pre-wrap font-sans line-clamp-3">
                  {v.content}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
