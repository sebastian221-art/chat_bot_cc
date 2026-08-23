// 📄 ARCHIVO: panel/middleware.ts  ← NUEVO
// Protección de rutas: redirige a /login si no hay token en cookie.
// El token se guarda también en cookie (desde login/page.tsx) para que
// middleware.ts pueda leerlo (no tiene acceso a localStorage).
import { NextRequest, NextResponse } from 'next/server'

// Rutas que NO requieren autenticación
const PUBLIC_ROUTES = ['/login', '/unauthorized']

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Permitir rutas públicas y archivos estáticos
  if (
    PUBLIC_ROUTES.some(r => pathname.startsWith(r)) ||
    pathname.startsWith('/_next') ||
    pathname.startsWith('/favicon')
  ) {
    return NextResponse.next()
  }

  // Leer token de cookie
  const token = request.cookies.get('cc_token')?.value

  if (!token) {
    const loginUrl = new URL('/login', request.url)
    loginUrl.searchParams.set('from', pathname)
    return NextResponse.redirect(loginUrl)
  }

  // Leer rol de cookie (guardada al hacer login)
  const role      = request.cookies.get('cc_role')?.value      || ''
  const username  = request.cookies.get('cc_username')?.value  || ''
  const storeType = request.cookies.get('cc_store_type')?.value || ''
  const storeId   = request.cookies.get('cc_store_id')?.value   || ''

  // Verificar permisos según ruta
  const unauthorized = _checkAccess(pathname, role, username, storeType, storeId)
  if (unauthorized) {
    return NextResponse.redirect(new URL('/unauthorized', request.url))
  }

  return NextResponse.next()
}

function _checkAccess(
  pathname: string,
  role: string,
  username: string,
  storeType: string,
  storeId: string,
): boolean {
  // "Flujo del Bot" es una página EXCLUSIVA del desarrollador — solo
  // la cuenta 'admin' puede entrar, sin importar el rol. Cualquier
  // otra cuenta (aunque sea admin de otro username) queda bloqueada.
  if (pathname.startsWith('/flujo-bot')) {
    return username !== 'admin'   // true = bloqueado
  }
  if (pathname.startsWith('/orquestador')) {
    return username !== 'admin'   // true = bloqueado
  }

  // admin ve todo lo demás
  if (role === 'admin') return false

  // supervisor: solo estas rutas
  if (role === 'supervisor') {
    const allowed = ['/dashboard', '/conversaciones', '/eventos', '/tiendas', '/marketing']
    if (allowed.some(p => pathname.startsWith(p))) return false
    return true   // todo lo demás: sin acceso
  }

  // Ya no existen paneles específicos por tipo de local ni por
  // parqueadero — el panel administrativo es de uso exclusivo del
  // personal del Centro Comercial (admin/supervisor).
  return true
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
}