export interface SizeStock {
  size: string
  quantity: number
}

export interface Product {
  product_id: string
  name: string
  garment_type: string
  category: string
  description: string
  // Color of the garment itself; `colors` also lists logo/lettering colors.
  primary_color: string | null
  colors: string[]
  search_tags: string[]
  image_url: string
  price: number
  total_stock: number
}

export interface ProductDetail extends Product {
  inventory: SizeStock[]
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Request failed (${res.status})`)
  return res.json() as Promise<T>
}

export const fetchProducts = () => getJson<Product[]>('/api/products')

export const fetchProduct = (id: string) =>
  getJson<ProductDetail>(`/api/products/${encodeURIComponent(id)}`)

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatReply {
  reply: string
  products: Product[]
  // Saved conversation this reply belongs to (null for guests).
  conversation_id: string | null
}

export interface PageInfo {
  path: string
  product_id: string | null
}

export interface SavedChatMessage {
  role: 'user' | 'assistant'
  content: string
  products: Product[]
  created_at: string // UTC, "YYYY-MM-DD HH:MM:SS"
}

export interface ChatConversation {
  conversation_id: string | null
  messages: SavedChatMessage[]
}

export interface ConversationSummary {
  conversation_id: string
  started_at: string
  last_message_at: string
  message_count: number
  preview: string
}

// Sends the new message, recent turns (used for guests), the page the customer
// is on (so the agent knows what "this" refers to), and the current saved
// conversation (null starts a new one).
export async function sendChatMessage(
  message: string,
  history: ChatTurn[],
  page: PageInfo,
  conversationId: string | null,
): Promise<ChatReply> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history: history.slice(-20), page, conversation_id: conversationId }),
  })
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json() as Promise<ChatReply>
}

export interface User {
  id: number
  first_name: string
  last_name: string
  email: string
}

export interface SignupData {
  first_name: string
  last_name: string
  email: string
  password: string
  confirm_password: string
}

// Turns FastAPI error bodies (a string or a list of field errors) into one message.
async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      return body.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, '')).join('. ')
    }
  } catch {
    // fall through
  }
  return `Request failed (${res.status})`
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json() as Promise<T>
}

export const signup = (data: SignupData) => postJson<User>('/api/auth/signup', data)

export const login = (email: string, password: string) =>
  postJson<User>('/api/auth/login', { email, password })

export async function logout(): Promise<void> {
  await fetch('/api/auth/logout', { method: 'POST' })
}

export const fetchChatHistory = (conversationId?: string) =>
  getJson<ChatConversation>(
    conversationId
      ? `/api/chat/history?conversation_id=${encodeURIComponent(conversationId)}`
      : '/api/chat/history',
  )

export const fetchConversations = () => getJson<ConversationSummary[]>('/api/chat/conversations')

export const fetchCurrentUser = () => getJson<User | null>('/api/auth/me')

export const formatPrice = (price: number) => `$${price.toFixed(2)}`
