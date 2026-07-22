// 📄 ARCHIVO: panel/app/panel/farmacia/[id]/layout.tsx
// FIX: eliminado <Sidebar/> duplicado. El Sidebar ya viene del layout padre
// (panel/app/panel/farmacia/layout.tsx). Este layout solo agrega el breadcrumb.
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export default function FarmaciaIdLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="px-6 pt-5 pb-1">
        <Link
          href="/panel/farmacia"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-emerald-400 transition-colors"
        >
          <ArrowLeft size={12} /> Volver a farmacias
        </Link>
      </div>
      {children}
    </>
  )
}