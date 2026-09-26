import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowRight, Brain, Inbox, LoaderCircle, RefreshCw, Sparkles } from 'lucide-react'
import { emailsApi } from '../api/emails'
import { SAMPLE_EMAILS } from '../data/sampleEmails'

export default function Onboarding() {
  const navigate = useNavigate()
  const [checkingInbox, setCheckingInbox] = useState(true)
  const [checkError, setCheckError] = useState<string | null>(null)
  const [creatingSamples, setCreatingSamples] = useState(false)
  const [sampleError, setSampleError] = useState<string | null>(null)
  const [createdCount, setCreatedCount] = useState(0)
  const isCreatingRef = useRef(false)
  const createdSamplesRef = useRef(new Set<string>())

  const checkInbox = useCallback(async () => {
    setCheckingInbox(true)
    setCheckError(null)
    try {
      const inbox = await emailsApi.list({ page: 1, page_size: 1 })
      if (inbox.total > 0) {
        navigate('/', { replace: true })
      }
    } catch {
      setCheckError('We could not check your inbox. Please try again.')
    } finally {
      setCheckingInbox(false)
    }
  }, [navigate])

  useEffect(() => {
    void checkInbox()
  }, [checkInbox])

  const exploreSamples = async () => {
    if (isCreatingRef.current) return

    isCreatingRef.current = true
    setCreatingSamples(true)
    setSampleError(null)

    try {
      for (const sample of SAMPLE_EMAILS) {
        if (createdSamplesRef.current.has(sample.label)) continue

        await emailsApi.create(sample.data)
        createdSamplesRef.current.add(sample.label)
        setCreatedCount(createdSamplesRef.current.size)
      }

      navigate('/', { replace: true })
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      const message = Array.isArray(detail)
        ? detail.map((item: any) => item.msg).join(', ')
        : typeof detail === 'string'
        ? detail
        : 'Please check your connection and retry.'
      setSampleError(`Could not finish creating the sample inbox. ${message}`)
    } finally {
      isCreatingRef.current = false
      setCreatingSamples(false)
    }
  }

  return (
    <div className="app-shell min-h-screen flex items-center justify-center px-5 py-12">
      <main className="w-full max-w-4xl">
        <header className="text-center mb-10 animate-fade-in">
          <div className="inline-flex items-center gap-3 mb-8">
            <div className="w-12 h-12 rounded-2xl bg-[#e0ad5d] flex items-center justify-center shadow-lg shadow-[#e0ad5d]/10">
              <Brain className="w-6 h-6 text-[#18232a]" />
            </div>
            <div className="text-left">
              <p className="text-lg font-bold text-[#f5f2ea]">AVEN</p>
              <p className="text-xs text-[#e0ad5d]">Email Intelligence</p>
            </div>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold text-[#f5f2ea]">Welcome to AVEN</h1>
          <p className="text-[#9caeb0] mt-3">Understand what matters. Know what to do next.</p>
        </header>

        {checkingInbox ? (
          <div className="flex items-center justify-center gap-3 text-sm text-[#9caeb0]" role="status">
            <LoaderCircle className="w-5 h-5 animate-spin text-[#e0ad5d]" />
            Checking your inbox...
          </div>
        ) : checkError ? (
          <div className="card max-w-lg mx-auto text-center" role="alert">
            <AlertCircle className="w-8 h-8 text-amber-400 mx-auto mb-3" />
            <p className="text-sm text-[#c8d0cb] mb-4">{checkError}</p>
            <button onClick={checkInbox} className="btn-secondary inline-flex items-center gap-2">
              <RefreshCw className="w-4 h-4" /> Retry
            </button>
          </div>
        ) : (
          <>
            <div className="grid md:grid-cols-2 gap-4 animate-fade-in">
              <section className="card flex flex-col">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="w-10 h-10 rounded-xl bg-[#e0ad5d]/15 flex items-center justify-center mb-5">
                      <Sparkles className="w-5 h-5 text-[#e0ad5d]" />
                    </div>
                    <h2 className="text-lg font-bold text-[#f5f2ea]">Explore Sample Inbox</h2>
                    <p className="text-sm text-[#9caeb0] mt-2">
                      Explore {SAMPLE_EMAILS.length} example emails, analyzed for your inbox.
                    </p>
                  </div>
                </div>
                {creatingSamples && (
                  <p className="text-xs text-[#9caeb0] mt-5" role="status">
                    Adding sample {createdCount + 1} of {SAMPLE_EMAILS.length}...
                  </p>
                )}
                {sampleError && (
                  <div className="mt-5 p-3 rounded-lg border border-red-500/30 bg-red-500/10" role="alert">
                    <p className="text-sm text-red-300">{sampleError}</p>
                  </div>
                )}
                <button
                  type="button"
                  onClick={exploreSamples}
                  disabled={creatingSamples}
                  aria-busy={creatingSamples}
                  className="btn-primary mt-6 w-full flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-wait"
                >
                  {creatingSamples ? (
                    <>
                      <LoaderCircle className="w-4 h-4 animate-spin" />
                      Creating Sample Inbox ({createdCount}/{SAMPLE_EMAILS.length})
                    </>
                  ) : sampleError ? (
                    <>
                      <RefreshCw className="w-4 h-4" />
                      Retry Sample Creation
                    </>
                  ) : (
                    <>
                      Explore Sample Inbox
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </section>

              <section className="card flex flex-col">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="w-10 h-10 rounded-xl bg-slate-500/15 flex items-center justify-center mb-5">
                      <Inbox className="w-5 h-5 text-[#9caeb0]" />
                    </div>
                    <h2 className="text-lg font-bold text-[#f5f2ea]">Start With Empty Inbox</h2>
                    <p className="text-sm text-[#9caeb0] mt-2">
                      Go straight to your inbox and add messages when you are ready.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/', { replace: true })}
                  disabled={creatingSamples}
                  className="btn-secondary mt-6 w-full flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  Start With Empty Inbox
                  <ArrowRight className="w-4 h-4" />
                </button>
              </section>
            </div>
          </>
        )}
      </main>
    </div>
  )
}