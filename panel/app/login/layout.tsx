// 📄 ARCHIVO: panel/app/login/layout.tsx  ← NUEVO
// Layout limpio sin Sidebar para la página de login
export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', background: '#09090b' }}>
      {children}
    </div>
  )
}