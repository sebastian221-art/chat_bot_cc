'use client'
// 📄 ARCHIVO: panel/components/Sidebar.tsx  ← REEMPLAZA EL TUYO
// CAMBIOS: muestra usuario logueado, botón logout, oculta secciones según rol
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState, useEffect } from 'react'
import {
  LayoutDashboard, Store, MessageSquare, CalendarDays,
  BarChart2, ShoppingBag, FileText, ChevronRight,
  Utensils, Shirt, Pill, Film, Gamepad2, Car,
  Building2, ChevronDown, LogOut, Users, Shield, BookOpen,
} from 'lucide-react'
import { getUser, clearAuth, getRoleLabel, type AuthUser } from '@/lib/auth'

const TOP_LINKS = [
  { href: '/dashboard',      label: 'Dashboard',      icon: LayoutDashboard, roles: ['admin', 'supervisor'] },
  { href: '/conversaciones', label: 'Conversaciones',  icon: MessageSquare,   roles: ['admin', 'supervisor'] },
  { href: '/domicilios',     label: 'Domicilios',      icon: ShoppingBag,     roles: ['admin'] },
  { href: '/eventos',        label: 'Eventos',          icon: CalendarDays,    roles: ['admin', 'supervisor'] },
  { href: '/tiendas',        label: 'Locales',          icon: Store,           roles: ['admin', 'supervisor'] },
  { href: '/conocimiento',   label: 'Base de Conocimiento', icon: BookOpen,    roles: ['admin', 'supervisor'] },
  { href: '/analytics',      label: 'Analytics',        icon: BarChart2,       roles: ['admin'] },
  { href: '/reportes',       label: 'Reportes',         icon: FileText,        roles: ['admin'] },
  { href: '/usuarios',       label: 'Usuarios',         icon: Users,           roles: ['admin'] },
]

const PANEL_LINKS = [
  { href: '/panel/restaurante',     label: 'Restaurantes', icon: Utensils, color: '#f97316', roles: ['admin'] },
  { href: '/panel/tienda',          label: 'Ropa y Moda',  icon: Shirt,    color: '#a78bfa', roles: ['admin'] },
  { href: '/panel/farmacia',        label: 'Farmacias',    icon: Pill,     color: '#34d399', roles: ['admin'] },
  { href: '/panel/cine',            label: 'Cine',         icon: Film,     color: '#60a5fa', roles: ['admin'] },
  { href: '/panel/entretenimiento', label: 'Happy City',   icon: Gamepad2, color: '#f472b6', roles: ['admin'] },
  { href: '/panel/parqueadero',     label: 'Parqueadero',  icon: Car,      color: '#fbbf24', roles: ['admin', 'parqueadero'] },
]

export default function Sidebar() {
  const pathname    = usePathname()
  const router      = useRouter()
  const [user, setUser]           = useState<AuthUser | null>(null)
  const [panelsOpen, setPanelsOpen] = useState(false)

  useEffect(() => {
    setUser(getUser())
    setPanelsOpen(pathname.startsWith('/panel') || pathname.startsWith('/locales'))
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

  // Para rol "local": mostrar solo el link a su panel propio
  const isLocal = role === 'local'

  const visibleTopLinks = TOP_LINKS.filter(l => l.roles.includes(role))
  const visiblePanelLinks = PANEL_LINKS.filter(l => l.roles.includes(role))

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

        {/* Links principales filtrados por rol */}
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

        {/* Sección paneles de locales — solo para admin, supervisor y parqueadero */}
        {!isLocal && (
          <>
            <div className="pt-4 pb-1">
              <p className="px-3 text-[10px] text-zinc-600 uppercase tracking-widest font-semibold">
                Paneles de locales
              </p>
            </div>

            {(role === 'admin' || role === 'supervisor') && (
              <Link href="/locales"
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all
                  ${pathname === '/locales' ? 'bg-indigo-600 text-white' : 'text-zinc-400 hover:text-white hover:bg-zinc-800'}`}>
                <Building2 size={16} />
                <span className="flex-1">Todos los locales</span>
                {pathname === '/locales' && <ChevronRight size={14} className="opacity-60" />}
              </Link>
            )}

            {visiblePanelLinks.length > 0 && (
              <>
                <button onClick={() => setPanelsOpen(v => !v)}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all text-zinc-400 hover:text-white hover:bg-zinc-800">
                  <span className="w-4 h-4" />
                  <span className="flex-1 text-left text-xs text-zinc-500">Gestionar por tipo</span>
                  <ChevronDown size={13} className={`transition-transform duration-200 ${panelsOpen ? 'rotate-180' : ''}`} />
                </button>

                {panelsOpen && (
                  <div className="ml-3 pl-3 border-l border-zinc-800 space-y-0.5">
                    {visiblePanelLinks.map(({ href, label, icon: Icon, color }) => {
                      const active = pathname.startsWith(href)
                      return (
                        <Link key={href} href={href}
                          className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-all
                            ${active ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-white hover:bg-zinc-800/70'}`}>
                          <Icon size={13} style={{ color: active ? color : undefined }} />
                          <span className="flex-1">{label}</span>
                          {active && <ChevronRight size={11} className="opacity-50" />}
                        </Link>
                      )
                    })}
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* Para rol local: acceso directo a su panel */}
        {isLocal && user?.store_type && user?.store_id && (
          <Link
            href={`/panel/${user.store_type}/${user.store_id}`}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all mt-2
              ${pathname.includes(user.store_id) ? 'bg-indigo-600 text-white' : 'text-zinc-400 hover:text-white hover:bg-zinc-800'}`}
          >
            <Building2 size={16} />
            <span className="flex-1">{user.store_name || 'Mi local'}</span>
            <ChevronRight size={14} className="opacity-60" />
          </Link>
        )}
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