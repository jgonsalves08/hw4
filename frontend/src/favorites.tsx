import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useAuth } from './auth'

interface FavoritesState {
  favorites: Set<string>
  isFavorite: (productId: string) => boolean
  toggleFavorite: (productId: string) => void
}

const FavoritesContext = createContext<FavoritesState | null>(null)

// Hearted products are kept in this browser's localStorage, separately for each
// account (and for guests), so logging in or out switches to that person's list.
const storageKey = (userId: number | null) => `cc_favorites_${userId ?? 'guest'}`

function load(key: string): Set<string> {
  try {
    const raw = localStorage.getItem(key)
    return new Set(raw ? (JSON.parse(raw) as string[]) : [])
  } catch {
    return new Set()
  }
}

export function FavoritesProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const key = storageKey(user?.id ?? null)
  const [favorites, setFavorites] = useState<Set<string>>(() => load(key))

  useEffect(() => setFavorites(load(key)), [key])

  function toggleFavorite(productId: string) {
    setFavorites((prev) => {
      const next = new Set(prev)
      if (next.has(productId)) next.delete(productId)
      else next.add(productId)
      localStorage.setItem(key, JSON.stringify([...next]))
      return next
    })
  }

  return (
    <FavoritesContext.Provider
      value={{ favorites, isFavorite: (id) => favorites.has(id), toggleFavorite }}
    >
      {children}
    </FavoritesContext.Provider>
  )
}

export function useFavorites(): FavoritesState {
  const ctx = useContext(FavoritesContext)
  if (!ctx) throw new Error('useFavorites must be used inside FavoritesProvider')
  return ctx
}
