// 📄 ARCHIVO: panel/app/local/[id]/layout.tsx
import Sidebar from '@/components/Sidebar'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#09090b' }}>
      <div style={{ width: '256px', flexShrink: 0 }}>
        <Sidebar />
      </div>
      <main style={{ flex: 1, minWidth: 0, overflowY: 'auto', minHeight: '100vh' }}>
        <div style={{ padding: '20px 24px 0' }}>
          <Link
            href="/domicilios"
            className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-white transition-colors"
          >
            <ArrowLeft size={12} /> Volver a Domicilios
          </Link>
        </div>
        {children}
      </main>
    </div>
  )
}