// 📄 ARCHIVO: panel/app/domicilios/page.tsx
'use client'
import { useEffect, useState } from 'react'
import {
  getDeliveryTransferStats, getDeliveryTransfers,
  getDeliveryManagementStats, getDeliveryManagements,
} from '@/lib/api'
import {
  RefreshCw, Send, TrendingUp, Clock, Store, ClipboardCheck,
  UserX, Lock, User, Phone, MapPin, ShoppingBag, CreditCard,
  ExternalLink, CheckCircle2, CircleDashed, XCircle,
} from 'lucide-react'
import StatCard from '@/components/StatCard'

interface Transfer {
  id: number
  phone_number: string
  store_name: string
  timestamp: string
}

interface Management {
  id: number
  phone_number: string
  store_name: string
  status: 'collecting' | 'completed' | 'closed'
  customer_name: string | null
  customer_phone: string | null
  address: string | null
  order_details: string | null
  payment_method: string | null
  generated_link: string | null
  created_at: string
  completed_at: string | null
}

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  completed:  { label: 'Completada',  color: 'text-emerald-400 bg-emerald-500/10', icon: CheckCircle2 },
  collecting: { label: 'En curso',    color: 'text-amber-400 bg-amber-500/10',    icon: CircleDashed },
  closed:     { label: 'Local cerrado', color: 'text-rose-400 bg-rose-500/10',     icon: XCircle },
}

export default function DomiciliosPage() {
  const [tab, setTab] = useState<'gestiones' | 'transferencias'>('gestiones')
  const [loading, setLoading] = useState(true)

  const [mgmtStats, setMgmtStats] = useState<any>(null)
  const [managements, setManagements] = useState<Management[]>([])

  const [transferStats, setTransferStats] = useState<any>(null)
  const [transfers, setTransfers] = useState<Transfer[]>([])

  const load = async () => {
    setLoading(true)
    try {
      const [ms, ml, ts, tl] = await Promise.all([
        getDeliveryManagementStats(),
        getDeliveryManagements(),
        getDeliveryTransferStats(),
        getDeliveryTransfers(),
      ])
      setMgmtStats(ms)
      setManagements(ml)
      setTransferStats(ts)
      setTransfers(tl)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const fmtDate = (d: string) =>
    new Date(d).toLocaleString('es-CO', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })

  return (
    <div className="p-8">

      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-2xl font-bold text-white">Domicilios</h1>
          <p className="text-zinc-500 text-sm mt-0.5">Gestiones completas y transferencias hacia las tiendas</p>
        </div>
        <button onClick={load} className="p-2 text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-all">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-zinc-900 border border-zinc-800 rounded-xl p-1 w-fit">
        <button
          onClick={() => setTab('gestiones')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${tab === 'gestiones' ? 'bg-indigo-600 text-white' : 'text-zinc-400 hover:text-white'}`}
        >
          Gestiones completas
        </button>
        <button
          onClick={() => setTab('transferencias')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${tab === 'transferencias' ? 'bg-indigo-600 text-white' : 'text-zinc-400 hover:text-white'}`}
        >
          Transferencias simples
        </button>
      </div>

      {loading ? (
        <div className="text-center text-zinc-600 py-16 animate-pulse">Cargando...</div>

      ) : tab === 'gestiones' ? (
        <>
          {/* Aviso de cómo funciona */}
          <div className="mb-6 p-3 bg-indigo-950/30 border border-indigo-900/40 rounded-xl flex items-start gap-2.5">
            <ClipboardCheck size={15} className="text-indigo-400 flex-shrink-0 mt-0.5" />
            <p className="text-zinc-400 text-xs leading-relaxed">
              Una "gestión completa" ocurre cuando el cliente pide explícitamente ayuda para gestionar su pedido —
              Any recolecta sus datos y arma un link de WhatsApp con el pedido ya escrito, listo para el local.
              Distinto de una simple mención, que solo da el contacto directo (ver pestaña de al lado).
            </p>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <StatCard icon={<CheckCircle2 size={20} />} label="Completadas hoy" value={mgmtStats?.total_today ?? 0} color="indigo" />
            <StatCard icon={<TrendingUp size={20} />} label="Últimos 7 días" value={mgmtStats?.total_this_week ?? 0} color="emerald" />
            <StatCard icon={<UserX size={20} />} label="Abandonadas (7 días)" value={mgmtStats?.abandoned_this_week ?? 0} color="amber" />
            <StatCard icon={<Lock size={20} />} label="Local cerrado (7 días)" value={mgmtStats?.closed_this_week ?? 0} color="red" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* Top tiendas */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 lg:col-span-1">
              <h2 className="text-white font-semibold text-sm mb-4 flex items-center gap-2">
                <Store size={15} className="text-violet-400" /> Top tiendas — gestiones completadas
              </h2>
              {(!mgmtStats?.top_stores || mgmtStats.top_stores.length === 0) ? (
                <p className="text-zinc-600 text-sm text-center py-8">Sin gestiones completadas todavía</p>
              ) : (
                <div className="space-y-2.5">
                  {mgmtStats.top_stores.map((s: any, i: number) => {
                    const max = mgmtStats.top_stores[0].total
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

            {/* Lista detallada de gestiones */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 lg:col-span-2">
              <h2 className="text-white font-semibold text-sm mb-4 flex items-center gap-2">
                <Clock size={15} className="text-indigo-400" /> Gestiones recientes — detalle completo
              </h2>
              {managements.length === 0 ? (
                <p className="text-zinc-600 text-sm text-center py-8">Sin gestiones registradas todavía</p>
              ) : (
                <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
                  {managements.map(m => {
                    const status = STATUS_CONFIG[m.status] || STATUS_CONFIG.collecting
                    const StatusIcon = status.icon
                    return (
                      <div key={m.id} className="bg-zinc-950 border border-zinc-800 rounded-xl p-4">
                        <div className="flex items-center justify-between mb-2.5">
                          <span className="text-white font-semibold text-sm">{m.store_name}</span>
                          <span className={`flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${status.color}`}>
                            <StatusIcon size={11} /> {status.label}
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 text-xs text-zinc-400 mb-2">
                          {m.customer_name && (
                            <span className="flex items-center gap-1.5"><User size={11} className="text-zinc-600" /> {m.customer_name}</span>
                          )}
                          {m.customer_phone && (
                            <span className="flex items-center gap-1.5"><Phone size={11} className="text-zinc-600" /> {m.customer_phone}</span>
                          )}
                          {m.address && (
                            <span className="flex items-center gap-1.5 truncate"><MapPin size={11} className="text-zinc-600 flex-shrink-0" /> {m.address}</span>
                          )}
                          {m.payment_method && (
                            <span className="flex items-center gap-1.5"><CreditCard size={11} className="text-zinc-600" /> {m.payment_method}</span>
                          )}
                        </div>

                        {m.order_details && (
                          <p className="flex items-start gap-1.5 text-xs text-zinc-300 bg-zinc-900 rounded-lg px-2.5 py-2 mb-2">
                            <ShoppingBag size={11} className="text-zinc-600 flex-shrink-0 mt-0.5" /> {m.order_details}
                          </p>
                        )}

                        <div className="flex items-center justify-between pt-1">
                          <span className="text-zinc-600 text-[11px]">{fmtDate(m.created_at)} · {m.phone_number}</span>
                          {m.generated_link && (
                            <a
                              href={m.generated_link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 font-medium"
                            >
                              Ver link <ExternalLink size={10} />
                            </a>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </>

      ) : (
        <>
          {/* Aviso */}
          <div className="mb-6 p-3 bg-indigo-950/30 border border-indigo-900/40 rounded-xl flex items-start gap-2.5">
            <Send size={15} className="text-indigo-400 flex-shrink-0 mt-0.5" />
            <p className="text-zinc-400 text-xs leading-relaxed">
              Una transferencia simple ocurre cuando el cliente solo menciona que quiere pedir de una tienda —
              Any le da el contacto directo, sin recolectar datos ni armar el pedido.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <StatCard icon={<Send size={20} />} label="Transferencias hoy" value={transferStats?.total_today ?? 0} color="indigo" />
            <StatCard icon={<TrendingUp size={20} />} label="Últimos 7 días" value={transferStats?.total_this_week ?? 0} color="emerald" />
            <StatCard icon={<Store size={20} />} label="Tiendas con transferencias" value={transferStats?.top_stores?.length ?? 0} color="violet" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
              <h2 className="text-white font-semibold text-sm mb-4 flex items-center gap-2">
                <Store size={15} className="text-violet-400" /> Top tiendas — últimos 7 días
              </h2>
              {(!transferStats?.top_stores || transferStats.top_stores.length === 0) ? (
                <p className="text-zinc-600 text-sm text-center py-8">Sin transferencias todavía</p>
              ) : (
                <div className="space-y-2.5">
                  {transferStats.top_stores.map((s: any, i: number) => {
                    const max = transferStats.top_stores[0].total
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
                      <span className="text-zinc-600">{fmtDate(t.timestamp)}</span>
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