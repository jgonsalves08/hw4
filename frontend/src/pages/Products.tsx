import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchProducts, formatPrice, type Product } from '../api'
import ProductCard from '../components/ProductCard'
import PriceRangeSlider from '../components/PriceRangeSlider'
import { CloseIcon, FilterIcon, HeartIcon, SearchIcon } from '../components/Icons'
import { useChatResults } from '../chatResults'
import { useFavorites } from '../favorites'
import { COLOR_GROUPS, garmentColorIs } from '../colors'

// Same order as backend/categories.py.
const CATEGORIES = ['Hoodies', 'Crewnecks', 'Quarter-Zips', 'T-Shirts', 'Long Sleeve', 'Fleece & Jackets']

const SORTS = {
  featured: { label: 'Featured', compare: () => 0 },
  'price-asc': { label: 'Price: low to high', compare: (a: Product, b: Product) => a.price - b.price },
  'price-desc': { label: 'Price: high to low', compare: (a: Product, b: Product) => b.price - a.price },
  name: { label: 'Name: A–Z', compare: (a: Product, b: Product) => a.name.localeCompare(b.name) },
} as const
type SortKey = keyof typeof SORTS

export default function Products() {
  const [products, setProducts] = useState<Product[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const { results, clearResults } = useChatResults()
  const { isFavorite } = useFavorites()
  // Filters live in the URL so they survive opening an item and pressing Back.
  const [params, setParams] = useSearchParams()

  useEffect(() => {
    fetchProducts()
      .then(setProducts)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  // Chat search results replace the full catalogue until the customer clears them.
  const base = results ? results.products : products

  // Slider ends always span the whole catalogue, cheapest to most expensive.
  const prices = products.map((p) => p.price)
  const minPrice = prices.length ? Math.floor(Math.min(...prices)) : 0
  const maxPrice = prices.length ? Math.ceil(Math.max(...prices)) : 0

  // Categories and colors are multi-select: each choice is its own URL param
  // (?category=Hoodies&category=Crewnecks). An item matches if it's in ANY chosen
  // category and has ANY chosen color.
  const categories = params.getAll('category')
  const colors = params.getAll('color')
  const query = params.get('q') ?? ''
  const favoritesOnly = params.get('fav') === '1'
  const inStockOnly = params.get('stock') === '1'
  const sort = (params.get('sort') ?? 'featured') as SortKey
  const low = Math.max(minPrice, Number(params.get('min') ?? minPrice))
  const high = Math.min(maxPrice, Number(params.get('max') ?? maxPrice))
  const priceActive = low > minPrice || high < maxPrice

  const categoryCounts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const p of base) c[p.category] = (c[p.category] ?? 0) + 1
    return c
  }, [base])

  const colorCounts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const g of COLOR_GROUPS) c[g.name] = base.filter((p) => garmentColorIs(p.primary_color, g.name)).length
    return c
  }, [base])

  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  const visible = base
    .filter(
      (p) =>
        (categories.length === 0 || categories.includes(p.category)) &&
        (colors.length === 0 || colors.some((c) => garmentColorIs(p.primary_color, c))) &&
        (!favoritesOnly || isFavorite(p.product_id)) &&
        (!inStockOnly || p.total_stock > 0) &&
        p.price >= low &&
        p.price <= high &&
        words.every((w) => `${p.name} ${p.description} ${p.colors.join(' ')}`.toLowerCase().includes(w)),
    )
    .sort(SORTS[sort]?.compare ?? SORTS.featured.compare)

  function setParam(key: string, value: string | null) {
    // Build on the latest URL params so quick successive changes don't overwrite each other.
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev)
        if (value === null || value === '') p.delete(key)
        else p.set(key, value)
        return p
      },
      { replace: true },
    )
  }

  function toggleValue(key: string, value: string) {
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev)
        const current = p.getAll(key)
        p.delete(key)
        const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value]
        next.forEach((v) => p.append(key, v))
        return p
      },
      { replace: true },
    )
  }

  function setPrice(l: number, h: number) {
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev)
        if (l > minPrice) p.set('min', String(l))
        else p.delete('min')
        if (h < maxPrice) p.set('max', String(h))
        else p.delete('max')
        return p
      },
      { replace: true },
    )
  }

  const pills = [
    ...categories.map((c) => ({ label: c, clear: () => toggleValue('category', c) })),
    priceActive && {
      label: `${formatPrice(low)} – ${formatPrice(high)}`,
      clear: () => setPrice(minPrice, maxPrice),
    },
    ...colors.map((c) => ({ label: c, clear: () => toggleValue('color', c) })),
    query && { label: `“${query}”`, clear: () => setParam('q', null) },
    favoritesOnly && { label: 'Favorites', clear: () => setParam('fav', null) },
    inStockOnly && { label: 'In stock', clear: () => setParam('stock', null) },
  ].filter(Boolean) as { label: string; clear: () => void }[]

  const resetFilters = () => setParams(sort !== 'featured' ? { sort } : {}, { replace: true })
  const title = results
    ? 'Chat results'
    : categories.length
      ? categories.join(', ')
      : favoritesOnly
        ? 'Your favorites'
        : 'All products'

  return (
    <div className="shop">
      <aside className={`shop-sidebar ${filtersOpen ? 'open' : ''}`} aria-label="Filters">
        <div className="sidebar-heading">
          <FilterIcon />
          <span>Filters</span>
          <button
            type="button"
            className="sidebar-close"
            onClick={() => setFiltersOpen(false)}
            aria-label="Close filters"
          >
            <CloseIcon />
          </button>
        </div>

        <label className="search-box">
          <SearchIcon />
          <input
            type="search"
            placeholder="Search products…"
            value={query}
            onChange={(e) => setParam('q', e.target.value)}
            aria-label="Search products"
          />
        </label>

        <section className="filter-group">
          <h3>Categories</h3>
          <ul className="category-list">
            <li>
              <button
                type="button"
                className={categories.length === 0 ? 'active' : ''}
                onClick={() => setParam('category', null)}
              >
                All products <span className="count">{base.length}</span>
              </button>
            </li>
            {CATEGORIES.filter((c) => categoryCounts[c]).map((c) => (
              <li key={c}>
                <button
                  type="button"
                  className={categories.includes(c) ? 'active' : ''}
                  aria-pressed={categories.includes(c)}
                  onClick={() => toggleValue('category', c)}
                >
                  {c} <span className="count">{categoryCounts[c]}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        {!loading && maxPrice > 0 && (
          <section className="filter-group">
            <h3>Price</h3>
            <PriceRangeSlider min={minPrice} max={maxPrice} low={low} high={high} onChange={setPrice} />
          </section>
        )}

        <section className="filter-group">
          <h3>Color</h3>
          <div className="color-tags">
            {COLOR_GROUPS.filter((g) => colorCounts[g.name]).map((g) => (
              <button
                type="button"
                key={g.name}
                className={`tag ${colors.includes(g.name) ? 'active' : ''}`}
                aria-pressed={colors.includes(g.name)}
                onClick={() => toggleValue('color', g.name)}
              >
                <span className="swatch" style={{ background: g.swatch }} />
                {g.name}
              </button>
            ))}
          </div>
        </section>

        <section className="filter-group">
          <h3>Show</h3>
          <div className="color-tags">
            <button
              type="button"
              className={`tag ${favoritesOnly ? 'active' : ''}`}
              aria-pressed={favoritesOnly}
              onClick={() => setParam('fav', favoritesOnly ? null : '1')}
            >
              <HeartIcon size={14} filled={favoritesOnly} /> Favorites
            </button>
            <button
              type="button"
              className={`tag ${inStockOnly ? 'active' : ''}`}
              aria-pressed={inStockOnly}
              onClick={() => setParam('stock', inStockOnly ? null : '1')}
            >
              In stock
            </button>
          </div>
        </section>
      </aside>

      <section className="shop-main">
        <div className="shop-header">
          <div>
            <h1>{title}</h1>
            {results && (
              <p className="results-query">
                {results.products.length} {results.products.length === 1 ? 'item' : 'items'} for “
                {results.query}”{' '}
                <button type="button" className="link-button" onClick={clearResults}>
                  Show all products
                </button>
              </p>
            )}
          </div>
          <div className="shop-tools">
            <button type="button" className="filters-toggle" onClick={() => setFiltersOpen(true)}>
              <FilterIcon /> Filters
            </button>
            <label className="sort-select">
              <span>Sort</span>
              <select value={sort} onChange={(e) => setParam('sort', e.target.value === 'featured' ? null : e.target.value)}>
                {Object.entries(SORTS).map(([key, s]) => (
                  <option key={key} value={key}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        {pills.length > 0 && (
          <div className="filter-pills">
            {pills.map((p) => (
              <button type="button" key={p.label} className="pill" onClick={p.clear}>
                {p.label} <CloseIcon size={12} />
              </button>
            ))}
            <button type="button" className="link-button" onClick={resetFilters}>
              Clear all
            </button>
          </div>
        )}

        {loading && <p className="muted">Loading products…</p>}
        {error && <p className="error">Couldn’t load products: {error}</p>}
        {!loading && !error && (
          <p className="filter-summary">
            Showing {visible.length} of {base.length}
          </p>
        )}
        {!loading && !error && visible.length === 0 && (
          <div className="empty-state">
            <p>{favoritesOnly && !pills.some((p) => p.label !== 'Favorites') ? 'You haven’t hearted any products yet.' : 'No items match these filters.'}</p>
            <button type="button" className="button secondary" onClick={resetFilters}>
              Clear filters
            </button>
          </div>
        )}

        <div className="product-grid">
          {visible.map((p, i) => (
            <ProductCard key={p.product_id} product={p} index={i} />
          ))}
        </div>
      </section>

      {filtersOpen && <div className="sidebar-backdrop" onClick={() => setFiltersOpen(false)} />}
    </div>
  )
}
