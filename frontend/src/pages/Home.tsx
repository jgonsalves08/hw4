import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchProducts, type Product } from '../api'

const HERO_PRODUCTS = ['basic-hoodie-big-yale', 'pierson-college-crewneck', 'boola-boola-t-shirt']
const CATEGORIES = ['Hoodies', 'Crewnecks', 'Quarter-Zips', 'T-Shirts', 'Long Sleeve', 'Fleece & Jackets']

// Placeholder copy — to be rewritten in your own voice.
export default function Home() {
  const [products, setProducts] = useState<Product[]>([])

  useEffect(() => {
    fetchProducts().then(setProducts).catch(() => setProducts([]))
  }, [])

  const heroItems = HERO_PRODUCTS.map((id) => products.find((p) => p.product_id === id)).filter(
    (p): p is Product => !!p,
  )
  const tiles = CATEGORIES.map((c) => ({
    name: c,
    count: products.filter((p) => p.category === c).length,
    image: products.find((p) => p.category === c)?.image_url,
  })).filter((t) => t.count > 0)

  return (
    <div className="home">
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow light">New Haven, CT</span>
          <h1>Bulldog pride, made comfortable.</h1>
          <p>
            Campus Customs carries Yale apparel for students, alumni, families, and anyone who
            bleeds blue — from game-day tees to residential college crewnecks.
          </p>
          <div className="hero-actions">
            <Link to="/products" className="button light">
              Shop the collection
            </Link>
            <Link to="/products?category=Hoodies" className="button ghost">
              Browse hoodies
            </Link>
          </div>
        </div>
        <div className="hero-gallery" aria-hidden="true">
          {heroItems.map((p, i) => (
            <div key={p.product_id} className={`hero-card hero-card-${i}`}>
              <img src={p.image_url} alt="" />
            </div>
          ))}
        </div>
      </section>

      <section className="home-section">
        <div className="section-heading">
          <h2>Shop by category</h2>
          <Link to="/products">View all →</Link>
        </div>
        <div className="category-tiles">
          {tiles.map((t) => (
            <Link key={t.name} to={`/products?category=${encodeURIComponent(t.name)}`} className="category-tile">
              <div className="category-tile-image">{t.image && <img src={t.image} alt="" loading="lazy" />}</div>
              <span className="category-tile-name">{t.name}</span>
              <span className="category-tile-count">{t.count} items</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="features">
        <div className="feature">
          <h2>Gear for every Bulldog</h2>
          <p>Hoodies, quarter-zips, fleeces, and tees for every season on campus.</p>
        </div>
        <div className="feature">
          <h2>Show your college</h2>
          <p>Rep your residential college, your team, or your graduate school.</p>
        </div>
        <div className="feature">
          <h2>Ask our assistant</h2>
          <p>Not sure what fits? Open the chat in the corner and we’ll help you find it.</p>
        </div>
      </section>
    </div>
  )
}
