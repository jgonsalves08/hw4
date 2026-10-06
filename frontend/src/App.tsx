import { BrowserRouter, Route, Routes } from 'react-router-dom'
import NavBar from './components/NavBar'
import ChatWidget from './components/ChatWidget'
import Home from './pages/Home'
import Products from './pages/Products'
import ProductPage from './pages/ProductPage'
import About from './pages/About'
import Login from './pages/Login'
import CreateAccount from './pages/CreateAccount'
import NotFound from './pages/NotFound'
import { AuthProvider } from './auth'
import { ChatResultsProvider } from './chatResults'
import { FavoritesProvider } from './favorites'

export default function App() {
  return (
    <AuthProvider>
      <FavoritesProvider>
        <ChatResultsProvider>
          <BrowserRouter>
            <NavBar />
            <main className="page">
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/products" element={<Products />} />
                <Route path="/products/:productId" element={<ProductPage />} />
                <Route path="/about" element={<About />} />
                <Route path="/login" element={<Login />} />
                <Route path="/create-account" element={<CreateAccount />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </main>
            <footer className="footer">
              <span className="footer-brand">Campus Customs</span>
              <span>Yale apparel · New Haven, CT</span>
              <span>© {new Date().getFullYear()}</span>
            </footer>
            <ChatWidget />
          </BrowserRouter>
        </ChatResultsProvider>
      </FavoritesProvider>
    </AuthProvider>
  )
}
