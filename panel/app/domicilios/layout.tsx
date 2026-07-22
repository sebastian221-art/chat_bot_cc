// 📄 ARCHIVO: panel/app/domicilios/layout.tsx
import Sidebar from '@/components/Sidebar'

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#09090b' }}>
      <div style={{ width: '256px', flexShrink: 0 }}>
        <Sidebar />
      </div>
      <main style={{ flex: 1, minWidth: 0, overflowY: 'auto', minHeight: '100vh' }}>
        {children}
      </main>
    </div>
  )
}