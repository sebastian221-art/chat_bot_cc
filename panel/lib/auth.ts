// 📄 ARCHIVO: panel/lib/auth.ts  ← NUEVO
/**
 * Helpers de autenticación para el panel.
 * Guarda el JWT en localStorage y expone utilidades para leer el usuario.
 */

export interface AuthUser {
  id:         number
  username:   string
  full_name:  string
  role:       'admin' | 'local' | 'supervisor' | 'parqueadero'
  store_name: string | null
  store_type: string | null
  store_id:   string | null
}

const TOKEN_KEY = 'cc_panel_token'
const USER_KEY  = 'cc_panel_user'

// ── Guardar / limpiar ─────────────────────────────────────────────

export function saveAuth(token: string, user: AuthUser) {
  if (typeof window === 'undefined') return
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearAuth() {
  if (typeof window === 'undefined') return
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// ── Leer ──────────────────────────────────────────────────────────

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser(): AuthUser | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function isLoggedIn(): boolean {
  return !!getToken() && !!getUser()
}

// ── Permisos por rol ──────────────────────────────────────────────

export function canAccess(user: AuthUser | null, route: string): boolean {
  if (!user) return false
  const r = user.role

  if (r === 'admin') return true   // admin ve todo

  if (r === 'supervisor') {
    const allowed = ['/dashboard', '/conversaciones', '/eventos', '/tiendas', '/locales']
    return allowed.some(p => route.startsWith(p))
  }

  if (r === 'parqueadero') {
    return route.startsWith('/panel/parqueadero')
  }

  if (r === 'local') {
    // Solo puede entrar a su propio panel
    if (user.store_type && user.store_id) {
      return route.startsWith(`/panel/${user.store_type}/${user.store_id}`)
    }
    return false
  }

  return false
}

export function getHomeRoute(user: AuthUser): string {
  if (user.role === 'admin')       return '/dashboard'
  if (user.role === 'supervisor')  return '/dashboard'
  if (user.role === 'parqueadero') return '/panel/parqueadero'
  if (user.role === 'local' && user.store_type && user.store_id) {
    return `/panel/${user.store_type}/${user.store_id}`
  }
  return '/locales'
}

export function logout() {
  clearAuth()
}

export function getRoleLabel(role: string): string {
  const labels: Record<string, string> = {
    admin:       'Administrador',
    local:       'Dueño de local',
    supervisor:  'Supervisor CC',
    parqueadero: 'Parqueadero',
  }
  return labels[role] ?? role
}