import { Link } from 'react-router-dom'
import { formatPrice, type Product } from '../api'
import { useFavorites } from '../favorites'
import { HeartIcon } from './Icons'

function tagline(product: Product): string {
  return product.primary_color ? `${product.category} · ${product.primary_color}` : product.category
}

// Used by both the full Products grid and chat search results, so every card
// opens the same single-item page.
export default function ProductCard({ product, index = 0 }: { product: Product; index?: number }) {
  const { isFavorite, toggleFavorite } = useFavorites()
  const liked = isFavorite(product.product_id)

  return (
    <article className="product-card" style={{ '--i': Math.min(index, 12) } as React.CSSProperties}>
      <Link to={`/products/${product.product_id}`} className="product-card-link">
        <div className="product-card-image">
          <img src={product.image_url} alt={product.name} loading="lazy" />
          {product.total_stock === 0 && <span className="badge">Sold out</span>}
        </div>
        <div className="product-card-body">
          <div>
            <h2>{product.name}</h2>
            <p className="tagline">{tagline(product)}</p>
          </div>
          <p className="price">{formatPrice(product.price)}</p>
        </div>
        <p className="short-desc">{product.description}</p>
      </Link>
      <button
        type="button"
        className={`heart-button ${liked ? 'liked' : ''}`}
        onClick={() => toggleFavorite(product.product_id)}
        aria-pressed={liked}
        aria-label={liked ? `Remove ${product.name} from favorites` : `Add ${product.name} to favorites`}
      >
        <HeartIcon filled={liked} />
      </button>
    </article>
  )
}
