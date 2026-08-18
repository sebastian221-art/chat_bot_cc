'use client'
// 📄 ARCHIVO: panel/components/Sidebar.tsx
// LIMPIEZA: se eliminaron los paneles por tipo de local (Restaurantes,
// Ropa y Moda, Farmacias, Cine, Happy City, Parqueadero) y el link
// duplicado "Todos los locales" — ya no aplica, todo se maneja desde
// la página única de Locales, y no hay cuentas de acceso por local.
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState, useEffect } from 'react'
import {
  LayoutDashboard, Store, MessageSquare, CalendarDays,
  BarChart2, ShoppingBag, FileText, ChevronRight,
  Building2, LogOut, Users, Shield, BookOpen, QrCode, Gift, Megaphone,
} from 'lucide-react'
import { getUser, clearAuth, getRoleLabel, type AuthUser } from '@/lib/auth'

const TOP_LINKS = [
  { href: '/dashboard',      label: 'Dashboard',      icon: LayoutDashboard, roles: ['admin', 'supervisor'] },
  { href: '/conversaciones', label: 'Conversaciones',  icon: MessageSquare,   roles: ['admin', 'supervisor'] },
  { href: '/domicilios',     label: 'Domicilios',      icon: ShoppingBag,     roles: ['admin'] },
  { href: '/eventos',        label: 'Eventos',          icon: CalendarDays,    roles: ['admin', 'supervisor'] },
  { href: '/sorteos',        label: 'Sorteos',          icon: Gift,            roles: ['admin', 'supervisor'] },
  { href: '/marketing',      label: 'Marketing',        icon: Megaphone,       roles: ['admin', 'supervisor'] },
  { href: '/tiendas',        label: 'Locales',          icon: Store,           roles: ['admin', 'supervisor'] },
  { href: '/conocimiento',   label: 'Base de Conocimiento', icon: BookOpen,    roles: ['admin', 'supervisor'] },
  { href: '/zonas',          label: 'Navegación QR',       icon: QrCode,       roles: ['admin', 'supervisor'] },
  { href: '/info-general',   label: 'Info General',        icon: Building2,    roles: ['admin', 'supervisor'] },
  { href: '/analytics',      label: 'Analytics',        icon: BarChart2,       roles: ['admin'] },
  { href: '/reportes',       label: 'Reportes',         icon: FileText,        roles: ['admin'] },
  { href: '/usuarios',       label: 'Usuarios',         icon: Users,           roles: ['admin'] },
]

export default function Sidebar() {
  const pathname = usePathname()
  const router    = useRouter()
  const [user, setUser] = useState<AuthUser | null>(null)

  useEffect(() => {
    setUser(getUser())
  }, [pathname])

  function handleLogout() {
    clearAuth()
    // Limpiar cookies también
    ;['cc_token', 'cc_role', 'cc_store_type', 'cc_store_id'].forEach(name => {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`
    })
    router.replace('/login')
  }

  const role = user?.role || 'admin'
  const visibleTopLinks = TOP_LINKS.filter(l => l.roles.includes(role))

  return (
    <aside className="w-64 min-h-screen bg-zinc-950 border-r border-zinc-800 flex flex-col">

      {/* Logo */}
      <div className="px-6 py-6 border-b border-zinc-800">
        <p className="text-xs text-zinc-500 uppercase tracking-widest mb-1">Panel Admin</p>
        <h1 className="text-white font-bold text-lg leading-tight">CC El Puente 🛍️</h1>
        <div className="flex items-center gap-2 mt-3">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span className="text-xs text-zinc-400">Bot activo</span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {visibleTopLinks.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href)
          return (
            <Link key={href} href={href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all
                ${active ? 'bg-indigo-600 text-white' : 'text-zinc-400 hover:text-white hover:bg-zinc-800'}`}>
              <Icon size={16} />
              <span className="flex-1">{label}</span>
              {active && <ChevronRight size={14} className="opacity-60" />}
            </Link>
          )
        })}
      </nav>

      {/* Footer: usuario + logout */}
      {user && (
        <div className="border-t border-zinc-800 p-3">
          <div className="flex items-center gap-3 px-2 py-2 rounded-lg">
            <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
              {(user.full_name || user.username).charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-white font-medium truncate">
                {user.full_name || user.username}
              </p>
              <p className="text-[10px] text-zinc-500 truncate flex items-center gap-1">
                <Shield size={9} />
                {getRoleLabel(user.role)}
              </p>
            </div>
            <button
              onClick={handleLogout}
              title="Cerrar sesión"
              className="text-zinc-500 hover:text-red-400 transition-colors flex-shrink-0"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      )}
    </aside>
  )
}