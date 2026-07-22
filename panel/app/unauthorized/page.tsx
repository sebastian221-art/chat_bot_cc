'use client'
// 📄 ARCHIVO: panel/app/unauthorized/page.tsx  ← NUEVO
import { useRouter } from 'next/navigation'
import { getUser, getHomeRoute } from '@/lib/auth'

export default function UnauthorizedPage() {
  const router  = useRouter()
  const user    = getUser()

  function goHome() {
    if (user) {
      router.replace(getHomeRoute(user))
    } else {
      router.replace('/login')
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#09090b',
      flexDirection: 'column',
      gap: 16,
      textAlign: 'center',
      padding: 24,
    }}>
      <div style={{ fontSize: 48 }}>🔒</div>
      <h1 style={{ color: '#fff', fontSize: 22, fontWeight: 700, margin: 0 }}>
        Sin acceso
      </h1>
      <p style={{ color: '#71717a', fontSize: 14, maxWidth: 320, margin: 0 }}>
        Tu cuenta no tiene permiso para ver esta sección.
        {user && (
          <> Estás ingresado como <strong style={{ color: '#a1a1aa' }}>{user.full_name || user.username}</strong>.</>
        )}
      </p>
      <button
        onClick={goHome}
        style={{
          marginTop: 8,
          padding: '10px 24px',
          borderRadius: 10,
          border: 'none',
          background: '#6366f1',
          color: '#fff',
          fontSize: 14,
          fontWeight: 600,
          cursor: 'pointer',
        }}
      >
        Ir a mi panel
      </button>
    </div>
  )
}