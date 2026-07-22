// 📄 ARCHIVO: panel/app/locales/page.tsx
'use client'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { getStores } from '@/lib/api'
import { Utensils, Shirt, Pill, Film, Gamepad2, Car, ChevronRight, MapPin, ShoppingBag, Sparkles } from 'lucide-react'

const PANEL_TYPES = [
  { key:'restaurante', label:'Restaurantes y Cafeterías', desc:'Menú, domicilios, pedidos y horarios',         icon:Utensils, color:'#f97316', glow:'rgba(249,115,22,0.12)',  border:'rgba(249,115,22,0.2)',  categories:['Comida Rápida','Restaurante','Cafetería'],                                          href:'/panel/restaurante' },
  { key:'tienda',      label:'Ropa, Calzado y Moda',      desc:'Catálogo, novedades y productos',              icon:Shirt,    color:'#a78bfa', glow:'rgba(167,139,250,0.12)', border:'rgba(167,139,250,0.2)', categories:['Ropa y Calzado','Ropa y Moda','Ropa Mujer','Ropa y Calzado Deportivo','Accesorios'], href:'/panel/tienda' },
  { key:'farmacia',    label:'Farmacias y Salud',          desc:'Productos, disponibilidad y domicilios',       icon:Pill,     color:'#34d399', glow:'rgba(52,211,153,0.12)',  border:'rgba(52,211,153,0.2)',  categories:['Farmacia y Salud','Salud y Óptica'],                                               href:'/panel/farmacia' },
  { key:'cine',        label:'Cine',                       desc:'Cartelera, funciones y disponibilidad',        icon:Film,     color:'#60a5fa', glow:'rgba(96,165,250,0.12)',  border:'rgba(96,165,250,0.2)',  categories:[],                                                                                 href:'/panel/cine',        single:true },
  { key:'happy',       label:'Happy City',                 desc:'Actividades, aforo en vivo y horarios',        icon:Gamepad2, color:'#f472b6', glow:'rgba(244,114,182,0.12)', border:'rgba(244,114,182,0.2)', categories:[],                                                                                 href:'/panel/entretenimiento', single:true },
  { key:'parking',     label:'Parqueadero',                desc:'Espacios, ocupación, tarifas y cobro',         icon:Car,      color:'#fbbf24', glow:'rgba(251,191,36,0.12)',  border:'rgba(251,191,36,0.2)',  categories:[],                                                                                 href:'/panel/parqueadero', single:true },
]

export default function LocalesPage() {
  const [stores, setStores] = useState<any[]>([])
  useEffect(() => { getStores().then((d:any[]) => setStores(d)).catch(() => {}) }, [])

  const countFor = (cats:string[]) => cats.length===0 ? null : stores.filter(s=>cats.includes(s.category)).length
  const deliveryStores = stores.filter(s => ['Comida Rápida','Restaurante','Cafetería','Farmacia y Salud','Salud y Óptica'].includes(s.category))

  return (
    <div className="p-6 space-y-8">
      <div>
        <p className="text-zinc-500 text-xs uppercase tracking-widest font-semibold mb-1">CC El Puente</p>
        <h1 className="text-3xl font-bold text-white">Paneles de locales</h1>
        <p className="text-zinc-400 text-sm mt-1.5">Gestiona cada tipo de local desde su panel dedicado. Los cambios se reflejan en el bot automáticamente.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {PANEL_TYPES.map(pt => {
          const Icon  = pt.icon
          const count = countFor(pt.categories)
          return (
            <Link key={pt.key} href={pt.href}
              className="group relative bg-zinc-900 border border-zinc-800 hover:border-zinc-600 rounded-2xl p-5 transition-all duration-200 hover:shadow-xl flex items-start gap-4 overflow-hidden">
              <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none rounded-2xl"
                style={{ background:`radial-gradient(ellipse at top left, ${pt.glow}, transparent 70%)` }}/>
              <div className="relative w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 transition-transform group-hover:scale-110 duration-200"
                style={{ background:pt.glow, border:`1px solid ${pt.border}` }}>
                <Icon size={22} style={{ color:pt.color }}/>
              </div>
              <div className="relative flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-white font-semibold">{pt.label}</p>
                  <ChevronRight size={16} className="text-zinc-600 group-hover:text-zinc-300 transition-colors flex-shrink-0"/>
                </div>
                <p className="text-zinc-500 text-xs mt-0.5 leading-relaxed">{pt.desc}</p>
                {count !== null && (
                  <span className="inline-block mt-2 text-xs px-2 py-0.5 rounded-full font-medium"
                    style={{ color:pt.color, background:pt.glow, border:`1px solid ${pt.border}` }}>
                    {count} local{count!==1?'es':''}
                  </span>
                )}
                {(pt as any).single && (
                  <div className="flex items-center gap-1 mt-2">
                    <Sparkles size={10} style={{ color:pt.color }}/>
                    <span className="text-xs" style={{ color:pt.color }}>Panel único</span>
                  </div>
                )}
              </div>
            </Link>
          )
        })}
      </div>

      {deliveryStores.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <ShoppingBag size={14} className="text-indigo-400"/>
            <p className="text-zinc-400 text-xs uppercase tracking-widest font-semibold">Acceso rápido — Locales con domicilio</p>
          </div>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-2">
            {deliveryStores.slice(0,8).map((s:any, i:number) => (
              <Link key={i} href={`/local/${encodeURIComponent(s.name)}`}
                className="bg-zinc-900 border border-zinc-800 hover:border-indigo-500/40 rounded-xl px-3 py-3 transition-all group">
                <p className="text-white text-xs font-semibold truncate group-hover:text-indigo-400 transition-colors">{s.name}</p>
                <p className="text-zinc-600 text-xs mt-1 flex items-center gap-1"><MapPin size={9}/> {s.floor}</p>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="bg-indigo-500/5 border border-indigo-500/10 rounded-2xl p-4">
        <p className="text-indigo-300 text-xs font-semibold mb-1">💡 ¿Cómo funciona?</p>
        <p className="text-zinc-400 text-sm leading-relaxed">
          Cada panel está conectado con el bot de WhatsApp. Cuando actualizas precios, disponibilidad o cartelera, el bot responde con la info actualizada en tiempo real.
        </p>
      </div>
    </div>
  )
}