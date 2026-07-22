'use client'
// 📄 ARCHIVO: panel/app/login/page.tsx  ← NUEVO
import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { login as apiLogin } from '@/lib/api'
import { saveAuth, getHomeRoute, type AuthUser } from '@/lib/auth'

export default function LoginPage() {
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const data = await apiLogin(username, password)

      // Guardar en localStorage
      saveAuth(data.token, data.user as AuthUser)

      // Guardar en cookies para que middleware.ts pueda leerlas
      _setCookie('cc_token',      data.token,                 7)
      _setCookie('cc_role',       data.user.role,             7)
      _setCookie('cc_store_type', data.user.store_type || '', 7)
      _setCookie('cc_store_id',   data.user.store_id   || '', 7)

      // Redirigir según rol
      const dest = getHomeRoute(data.user as AuthUser)
      router.replace(dest)

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error desconocido'
      if (msg.includes('401')) {
        setError('Usuario o contraseña incorrectos')
      } else {
        setError('No se pudo conectar al servidor. ¿Está corriendo el backend?')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#09090b',
      padding: '24px',
    }}>
      <div style={{ width: '100%', maxWidth: '380px' }}>

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: '40px' }}>
          <div style={{
            width: 56, height: 56,
            borderRadius: 16,
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 24, margin: '0 auto 16px',
          }}>
            🛍️
          </div>
          <h1 style={{ color: '#fff', fontSize: 22, fontWeight: 700, margin: 0 }}>
            CC El Puente
          </h1>
          <p style={{ color: '#71717a', fontSize: 13, marginTop: 6 }}>
            Panel de administración
          </p>
        </div>

        {/* Card */}
        <div style={{
          background: '#18181b',
          border: '1px solid #27272a',
          borderRadius: 16,
          padding: '32px 28px',
        }}>
          <h2 style={{ color: '#fff', fontSize: 16, fontWeight: 600, margin: '0 0 24px' }}>
            Iniciar sesión
          </h2>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

            <div>
              <label style={{ display: 'block', color: '#a1a1aa', fontSize: 12, marginBottom: 6, fontWeight: 500 }}>
                Usuario
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Ej: admin"
                required
                autoFocus
                style={inputStyle}
              />
            </div>

            <div>
              <label style={{ display: 'block', color: '#a1a1aa', fontSize: 12, marginBottom: 6, fontWeight: 500 }}>
                Contraseña
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                style={inputStyle}
              />
            </div>

            {error && (
              <div style={{
                background: '#3f1212',
                border: '1px solid #7f1d1d',
                borderRadius: 8,
                padding: '10px 14px',
                color: '#fca5a5',
                fontSize: 13,
              }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                marginTop: 4,
                padding: '11px 0',
                borderRadius: 10,
                border: 'none',
                background: loading ? '#3f3f46' : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                color: loading ? '#71717a' : '#fff',
                fontSize: 14,
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'all .2s',
              }}
            >
              {loading ? 'Ingresando...' : 'Ingresar'}
            </button>

          </form>
        </div>

        <p style={{ textAlign: 'center', color: '#3f3f46', fontSize: 11, marginTop: 20 }}>
          CC El Puente · Sistema de gestión v3.0
        </p>
      </div>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 13px',
  background: '#09090b',
  border: '1px solid #27272a',
  borderRadius: 8,
  color: '#fff',
  fontSize: 14,
  outline: 'none',
  boxSizing: 'border-box',
  transition: 'border-color .2s',
}

function _setCookie(name: string, value: string, days: number) {
  const expires = new Date()
  expires.setDate(expires.getDate() + days)
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires.toUTCString()}; path=/; SameSite=Lax`
}