// 📄 ARCHIVO: panel/app/panel/tienda/page.tsx
'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { getStores } from '@/lib/api'
import { ChevronRight, Shirt, MapPin } from 'lucide-react'

export default function TiendaListPage() {
  const [stores, setStores] = useState<any[]>([])
  useEffect(() => {
    getStores().then((all:any[]) =>
      setStores(all.filter(s => ['Ropa y Calzado','Ropa y Moda','Ropa Mujer','Ropa y Calzado Deportivo','Accesorios y Maletas'].includes(s.category)))
    ).catch(() => {})
  }, [])

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2"><Shirt size={20} className="text-violet-400"/> Ropa, Calzado y Moda</h1>
        <p className="text-zinc-500 text-sm mt-0.5">Selecciona el local para gestionar su catálogo</p>
      </div>
      {stores.length === 0
        ? <p className="text-zinc-500 text-sm py-12 text-center">No hay locales registrados en estas categorías.</p>
        : <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {stores.map((s,i) => (
              <Link key={i} href={`/panel/tienda/${encodeURIComponent(s.name)}`}
                className="group bg-zinc-900 border border-zinc-800 hover:border-violet-500/30 rounded-2xl p-4 flex items-center gap-4 transition-all hover:shadow-lg">
                <div className="w-10 h-10 bg-violet-500/10 rounded-xl flex items-center justify-center flex-shrink-0">
                  <Shirt size={16} className="text-violet-400"/>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white font-semibold text-sm group-hover:text-violet-400 transition-colors">{s.name}</p>
                  <p className="text-zinc-500 text-xs flex items-center gap-1 mt-0.5"><MapPin size={9}/>{s.floor} · {s.category}</p>
                </div>
                <ChevronRight size={15} className="text-zinc-600 group-hover:text-zinc-300 flex-shrink-0 transition-colors"/>
              </Link>
            ))}
          </div>
      }
    </div>
  )
}