import { Fragment, useEffect, useRef, useState, type FormEvent } from 'react'
import { matchPath, useLocation, useNavigate } from 'react-router-dom'
import {
  fetchChatHistory,
  fetchConversations,
  sendChatMessage,
  type ChatTurn,
  type ConversationSummary,
  type Product,
  type SavedChatMessage,
} from '../api'
import { useAuth } from '../auth'
import { useChatResults } from '../chatResults'
import ChatMarkdown from './ChatMarkdown'
import { ChatIcon, ClockIcon, CloseIcon, PlusIcon, SendIcon } from './Icons'

interface Message extends ChatTurn {
  // When the message was sent (shown as date dividers and times).
  createdAt: Date
  // Product cards that came with this reply (UI only, not sent as history).
  products?: Product[]
  // The customer message that produced them, used as the results heading.
  query?: string
  // Connection/error notices are shown but never sent to the agent as history.
  isError?: boolean
}

const SUGGESTIONS = [
  'What hoodies do you have?',
  'Show me T-shirts under $40',
  'What’s your most popular crewneck?',
]

// ---- Dates: the server stores UTC "YYYY-MM-DD HH:MM:SS"; show local time. ----
const parseUtc = (s: string) => new Date(s.replace(' ', 'T') + 'Z')

function dayLabel(d: Date): string {
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: d.getFullYear() === today.getFullYear() ? undefined : 'numeric',
  })
}

const timeLabel = (d: Date) => d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })

function greeting(firstName: string | null, resumed: boolean): Message {
  const content = resumed
    ? `Welcome back, ${firstName}! Here’s your last conversation — tap **New chat** to start fresh.`
    : firstName
      ? `Hi ${firstName}! I’m the Campus Customs assistant. Ask me about our gear.`
      : 'Hi! I’m the Campus Customs assistant. Ask me about our gear.'
  return { role: 'assistant', content, createdAt: new Date() }
}

const fromSaved = (saved: SavedChatMessage[]): Message[] =>
  saved.map((m, i) => ({
    role: m.role,
    content: m.content,
    createdAt: parseUtc(m.created_at),
    products: m.products,
    query: saved[i - 1]?.content,
  }))

export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [view, setView] = useState<'chat' | 'history'>('chat')
  const [messages, setMessages] = useState<Message[]>([greeting(null, false)])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const { showResults } = useChatResults()
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const currentProductId = matchPath('/products/:productId', location.pathname)?.params.productId

  // Logged-in customers get their most recent conversation back; logging out
  // (or switching accounts) starts a fresh guest chat.
  useEffect(() => {
    if (authLoading) return
    setView('chat')
    setConversations(null)
    setConversationId(null)
    if (!user) {
      setMessages([greeting(null, false)])
      return
    }
    let cancelled = false
    fetchChatHistory()
      .then((saved) => {
        if (cancelled) return
        setConversationId(saved.conversation_id)
        setMessages([greeting(user.first_name, saved.messages.length > 0), ...fromSaved(saved.messages)])
      })
      .catch(() => !cancelled && setMessages([greeting(user.first_name, false)]))
    return () => {
      cancelled = true
    }
  }, [user, authLoading])

  // Start a new conversation: the old one stays saved (and in History), but it's
  // hidden here and the assistant won't use it as memory.
  function startNewChat() {
    setConversationId(null)
    setMessages([greeting(user?.first_name ?? null, false)])
    setView('chat')
  }

  async function openHistory() {
    setView('history')
    setConversations(null)
    try {
      setConversations(await fetchConversations())
    } catch {
      setConversations([])
    }
  }

  async function openConversation(id: string) {
    try {
      const saved = await fetchChatHistory(id)
      setConversationId(saved.conversation_id)
      setMessages(fromSaved(saved.messages))
    } catch {
      startNewChat()
    }
    setView('chat')
  }

  function viewCards(products: Product[], query: string) {
    showResults({ query, products })
    navigate('/products')
  }

  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending, open, view])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    void send(input)
  }

  async function send(raw: string) {
    const text = raw.trim()
    if (!text || sending) return
    // Greetings and errors are UI-only, so they aren't sent as history (guests only).
    const history = messages
      .filter((m, i) => !m.isError && !(i === 0 && m.role === 'assistant'))
      .map(({ role, content }) => ({ role, content }))
    setMessages((m) => [...m, { role: 'user', content: text, createdAt: new Date() }])
    setInput('')
    setSending(true)
    try {
      const reply = await sendChatMessage(
        text,
        history,
        { path: location.pathname, product_id: currentProductId ?? null },
        conversationId,
      )
      setConversationId(reply.conversation_id)
      // Stay on a product page when the only card is the product already open.
      const onlyCurrentProduct =
        reply.products.length === 1 && reply.products[0].product_id === currentProductId
      const showCards = reply.products.length > 0 && !onlyCurrentProduct
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: reply.reply,
          createdAt: new Date(),
          products: showCards ? reply.products : [],
          query: text,
        },
      ])
      // Put the matching items on the Products page as clickable cards.
      if (showCards) viewCards(reply.products, text)
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: (err as Error).message, createdAt: new Date(), isError: true },
      ])
    } finally {
      setSending(false)
    }
  }

  const showSuggestions = !sending && messages.every((m) => m.role === 'assistant')

  return (
    <div className="chat">
      {open && (
        <section className="chat-panel" aria-label="Chat with Campus Customs">
          <header className="chat-header">
            <span className="chat-avatar" aria-hidden="true">
              CC
            </span>
            <div className="chat-title">
              <strong>Campus Customs Assistant</strong>
              <span className="chat-status">
                <span className="status-dot" /> Online
              </span>
            </div>
            <div className="chat-header-actions">
              <button
                type="button"
                className="chat-icon-button"
                onClick={startNewChat}
                aria-label="New chat"
                data-tooltip="Start a new chat"
              >
                <PlusIcon />
              </button>
              {user && (
                <button
                  type="button"
                  className={`chat-icon-button ${view === 'history' ? 'active' : ''}`}
                  onClick={() => (view === 'history' ? setView('chat') : void openHistory())}
                  aria-label="Past chats"
                  data-tooltip={view === 'history' ? 'Back to chat' : 'View past chats'}
                  aria-pressed={view === 'history'}
                >
                  <ClockIcon />
                </button>
              )}
              <button
                type="button"
                className="chat-icon-button"
                onClick={() => setOpen(false)}
                aria-label="Close chat"
                data-tooltip="Close chat"
              >
                <CloseIcon size={18} />
              </button>
            </div>
          </header>

          {view === 'history' ? (
            <div className="chat-history" ref={scrollRef}>
              <div className="chat-history-top">
                <h3>Past chats</h3>
                <button type="button" className="chat-new-button" onClick={startNewChat}>
                  <PlusIcon size={14} /> New chat
                </button>
              </div>
              {conversations === null && <p className="muted small">Loading…</p>}
              {conversations?.length === 0 && <p className="muted small">No saved chats yet.</p>}
              <ul>
                {conversations?.map((c) => {
                  const started = parseUtc(c.started_at)
                  return (
                    <li key={c.conversation_id}>
                      <button
                        type="button"
                        className={`chat-history-item ${c.conversation_id === conversationId ? 'current' : ''}`}
                        onClick={() => void openConversation(c.conversation_id)}
                      >
                        <span className="chat-history-date">
                          {dayLabel(started)} · {timeLabel(started)}
                          {c.conversation_id === conversationId && <span className="current-tag">Current</span>}
                        </span>
                        <span className="chat-history-preview">{c.preview || 'Conversation'}</span>
                        <span className="chat-history-count">{c.message_count} messages</span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          ) : (
            <div className="chat-messages" ref={scrollRef} aria-live="polite">
              {messages.map((m, i) => {
                const newDay = i === 0 || m.createdAt.toDateString() !== messages[i - 1].createdAt.toDateString()
                return (
                  <Fragment key={i}>
                    {newDay && (
                      <div className="chat-date-divider">
                        <span>{dayLabel(m.createdAt)}</span>
                      </div>
                    )}
                    <div className={`chat-row ${m.role}`}>
                      <div className={`chat-bubble ${m.role} ${m.isError ? 'error' : ''}`}>
                        {m.role === 'assistant' ? <ChatMarkdown text={m.content} /> : m.content}
                        {m.products?.length ? (
                          <button
                            type="button"
                            className="chat-cards-note"
                            onClick={() => viewCards(m.products!, m.query ?? 'earlier chat')}
                          >
                            View {m.products.length} {m.products.length === 1 ? 'item' : 'items'} →
                          </button>
                        ) : null}
                      </div>
                    </div>
                    <span className={`chat-time ${m.role}`}>{timeLabel(m.createdAt)}</span>
                  </Fragment>
                )
              })}
              {sending && (
                <div className="chat-row assistant">
                  <div className="chat-bubble assistant typing" aria-label="Assistant is typing">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              )}
              {showSuggestions && (
                <div className="chat-suggestions">
                  {SUGGESTIONS.map((q) => (
                    <button type="button" key={q} onClick={() => void send(q)}>
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {view === 'chat' && (
            <form className="chat-input" onSubmit={handleSubmit}>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about sizes, colors, prices…"
                aria-label="Chat message"
              />
              <button type="submit" disabled={sending || !input.trim()} aria-label="Send message">
                <SendIcon />
              </button>
            </form>
          )}
        </section>
      )}
      <button
        type="button"
        className={`chat-toggle ${open ? 'open' : ''}`}
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Close chat' : 'Open chat'}
      >
        {open ? <CloseIcon size={22} /> : <ChatIcon />}
      </button>
    </div>
  )
}
