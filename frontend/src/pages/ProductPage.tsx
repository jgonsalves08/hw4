import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { fetchProduct, formatPrice, type ProductDetail } from '../api'
import { useFavorites } from '../favorites'
import { ArrowLeftIcon, HeartIcon } from '../components/Icons'

const LOW_STOCK = 5

export default function ProductPage() {
  const { productId = '' } = useParams()
  const [product, setProduct] = useState<ProductDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { isFavorite, toggleFavorite } = useFavorites()
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    setProduct(null)
    setError(null)
    fetchProduct(productId)
      .then(setProduct)
      .catch((e: Error) => setError(e.message))
  }, [productId])

  // Go back to the filtered Products page when we came from it; otherwise open Products.
  const goBack = () => (location.key !== 'default' ? navigate(-1) : navigate('/products'))

  if (error) {
    return (
      <div className="detail-error">
        <p className="error">Couldn’t load this product: {error}</p>
        <Link to="/products" className="button secondary">
          Browse all products
        </Link>
      </div>
    )
  }
  if (!product) return <p className="muted">Loading…</p>

  const liked = isFavorite(product.product_id)
  const accents = product.colors.filter((c) => c !== product.primary_color)

  return (
    <div className="product-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <button type="button" className="back-link" onClick={goBack}>
          <ArrowLeftIcon /> Back
        </button>
        <span className="crumbs">
          <Link to="/products">Products</Link> /{' '}
          <Link to={`/products?category=${encodeURIComponent(product.category)}`}>{product.category}</Link> /{' '}
          <span aria-current="page">{product.name}</span>
        </span>
      </nav>

      <div className="product-detail">
        <div className="product-detail-image">
          <img src={product.image_url} alt={product.name} />
        </div>

        <div className="product-detail-info">
          <span className="eyebrow">{product.category}</span>
          <h1>{product.name}</h1>
          <p className="price large">{formatPrice(product.price)}</p>
          <p className="description">{product.description}</p>

          <div className="detail-section">
            <h2>Color</h2>
            <p className="detail-colors">{product.primary_color ?? 'See photo'}</p>
            {accents.length > 0 && <p className="detail-accents">Logo &amp; lettering: {accents.join(', ')}</p>}
          </div>

          {product.inventory.length > 0 && (
            <div className="detail-section">
              <h2>Sizes &amp; stock</h2>
              <ul className="size-grid">
                {product.inventory.map((s) => (
                  <li
                    key={s.size}
                    className={`size-tile ${s.quantity === 0 ? 'sold-out' : s.quantity <= LOW_STOCK ? 'low' : ''}`}
                  >
                    <span className="size">{s.size}</span>
                    <span className="qty">
                      {s.quantity === 0 ? 'Sold out' : s.quantity <= LOW_STOCK ? `Only ${s.quantity} left` : `${s.quantity} in stock`}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="total-stock">Total in stock: {product.total_stock}</p>
            </div>
          )}

          <button
            type="button"
            className={`button ${liked ? 'secondary' : ''} favorite-button`}
            onClick={() => toggleFavorite(product.product_id)}
            aria-pressed={liked}
          >
            <HeartIcon size={18} filled={liked} /> {liked ? 'Saved to favorites' : 'Add to favorites'}
          </button>
          <p className="muted small">Questions about fit or color? Ask our assistant in the corner.</p>
        </div>
      </div>
    </div>
  )
}
