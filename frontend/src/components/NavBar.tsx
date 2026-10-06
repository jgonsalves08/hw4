import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { useFavorites } from '../favorites'
import { HeartIcon, UserIcon } from './Icons'

const mainLinks = [
  { to: '/', label: 'Home' },
  { to: '/products', label: 'Products' },
  { to: '/about', label: 'About Us' },
]

const linkClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? 'nav-link active' : 'nav-link'

export default function NavBar() {
  const { user, loading, logout } = useAuth()
  const { favorites } = useFavorites()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/')
  }

  return (
    <header className="navbar">
      <Link to="/" className="brand" aria-label="Campus Customs home">
        <span className="brand-mark" aria-hidden="true">
          CC
        </span>
        <span className="brand-name">Campus Customs</span>
      </Link>

      <nav className="nav-main" aria-label="Main">
        {mainLinks.map((link) => (
          <NavLink key={link.to} to={link.to} end={link.to === '/'} className={linkClass}>
            {link.label}
          </NavLink>
        ))}
      </nav>

      <div className="nav-actions">
        <Link to="/products?fav=1" className="icon-link" aria-label={`Favorites (${favorites.size})`}>
          <HeartIcon />
          {favorites.size > 0 && <span className="icon-badge">{favorites.size}</span>}
        </Link>
        {!loading &&
          (user ? (
            <>
              <span className="nav-greeting">
                <UserIcon size={18} /> Hi, {user.first_name}
              </span>
              <button type="button" className="nav-button" onClick={handleLogout}>
                Log out
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login" className={linkClass}>
                Log in
              </NavLink>
              <NavLink to="/create-account" className="nav-cta">
                Create Account
              </NavLink>
            </>
          ))}
      </div>
    </header>
  )
}
