// 📄 ARCHIVO: panel/app/domicilios/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { getDeliveryTransferStats, getDeliveryTransfers } from '@/lib/api'
import { RefreshCw, Send, TrendingUp, Clock, Store } from 'lucide-react'
import StatCard from '@/components/StatCard'

interface Transfer {
  id: number
  phone_number: string
  store_name: string
  timestamp: string
}

export default function DomiciliosPage() {
  const [stats, setStats] = useState<any>(null)
  const [transfers, setTransfers] = useState<Transfer[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [statsData, transfersData] = await Promise.all([
        getDeliveryTransferStats(),
        getDeliveryTransfers(),
      ])
      setStats(statsData)
      setTransfers(transfersData)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="p-8">

      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Domicilios</h1>
          <p className="text-zinc-500 text-sm mt-0.5">
            Transferencias de clientes hacia el WhatsApp de cada tienda
          </p>
        </div>
        <button
          onClick={load}
          className="p-2 text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-all"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Aviso de cómo funciona ahora */}
      <div className="mb-6 p-3 bg-indigo-950/30 border border-indigo-900/40 rounded-xl flex items-start gap-2.5">
        <Send size={15} className="text-indigo-400 flex-shrink-0 mt-0.5" />
        <p className="text-zinc-400 text-xs leading-relaxed">
          Any ya no gestiona el pedido completo — cuando un cliente pide domicilio, lo transfiere directo al
          WhatsApp de la tienda para que ellos lo atiendan. Esta página muestra cuántas transferencias se están
          generando y hacia qué tiendas, no el estado de cada pedido (eso ya lo maneja cada local directamente).
        </p>
      </div>

      {/* Stats */}
      {loading ? (
        <div className="text-center text-zinc-600 py-16 animate-pulse">Cargando...</div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <StatCard
              icon={<Send size={20} />}
              label="Transferencias hoy"
              value={stats?.total_today ?? 0}
              color="indigo"
            />
            <StatCard
              icon={<TrendingUp size={20} />}
              label="Últimos 7 días"
              value={stats?.total_this_week ?? 0}
              color="emerald"
            />
            <StatCard
              icon={<Store size={20} />}
              label="Tiendas con transferencias"
              value={stats?.top_stores?.length ?? 0}
              color="violet"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* Top tiendas */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
              <h2 className="text-white font-semibold text-sm mb-4 flex items-center gap-2">
                <Store size={15} className="text-violet-400" /> Top tiendas — últimos 7 días
              </h2>
              {(!stats?.top_stores || stats.top_stores.length === 0) ? (
                <p className="text-zinc-600 text-sm text-center py-8">Sin transferencias todavía</p>
              ) : (
                <div className="space-y-2.5">
                  {stats.top_stores.map((s: any, i: number) => {
                    const max = stats.top_stores[0].total
                    const pct = Math.round((s.total / max) * 100)
                    return (
                      <div key={i}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-white font-medium">{i + 1}. {s.store}</span>
                          <span className="text-zinc-500">{s.total}</span>
                        </div>
                        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div className="h-full bg-violet-500 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Últimas transferencias */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
              <h2 className="text-white font-semibold text-sm mb-4 flex items-center gap-2">
                <Clock size={15} className="text-indigo-400" /> Últimas transferencias
              </h2>
              {transfers.length === 0 ? (
                <p className="text-zinc-600 text-sm text-center py-8">Sin transferencias todavía</p>
              ) : (
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {transfers.slice(0, 15).map(t => (
                    <div key={t.id} className="flex items-center justify-between text-xs py-2 border-b border-zinc-800/60 last:border-0">
                      <div>
                        <p className="text-white font-medium">{t.store_name}</p>
                        <p className="text-zinc-500 mt-0.5">{t.phone_number}</p>
                      </div>
                      <span className="text-zinc-600">
                        {new Date(t.timestamp).toLocaleString('es-CO', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        </>
      )}
    </div>
  )
}