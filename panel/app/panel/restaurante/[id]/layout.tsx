// 📄 ARCHIVO: panel/app/panel/restaurante/[id]/layout.tsx
// FIX: eliminado <Sidebar/> duplicado. El Sidebar ya viene del layout padre
// (panel/app/panel/restaurante/layout.tsx). Este layout solo agrega el breadcrumb.
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export default function RestauranteIdLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="px-6 pt-5 pb-1">
        <Link
          href="/panel/restaurante"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-orange-400 transition-colors"
        >
          <ArrowLeft size={12} /> Volver a restaurantes
        </Link>
      </div>
      {children}
    </>
  )
}