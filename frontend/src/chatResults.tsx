import { createContext, useContext, useState, type ReactNode } from 'react'
import type { Product } from './api'

export interface ChatResults {
  query: string
  products: Product[]
}

interface ChatResultsState {
  results: ChatResults | null
  showResults: (results: ChatResults) => void
  clearResults: () => void
}

const ChatResultsContext = createContext<ChatResultsState | null>(null)

// Holds the latest product cards the chat agent returned, so the Products page
// can show them and they survive navigating to an item page and back.
export function ChatResultsProvider({ children }: { children: ReactNode }) {
  const [results, setResults] = useState<ChatResults | null>(null)
  return (
    <ChatResultsContext.Provider
      value={{ results, showResults: setResults, clearResults: () => setResults(null) }}
    >
      {children}
    </ChatResultsContext.Provider>
  )
}

export function useChatResults(): ChatResultsState {
  const ctx = useContext(ChatResultsContext)
  if (!ctx) throw new Error('useChatResults must be used inside ChatResultsProvider')
  return ctx
}
