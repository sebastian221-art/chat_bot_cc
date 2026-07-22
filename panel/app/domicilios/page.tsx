// 📄 ARCHIVO: panel/app/domicilios/page.tsx
'use client'
import { useEffect, useState, useCallback } from 'react'
import { getOrders, getOrderStats, updateOrderStatus, OrderStats } from '@/lib/api'
import { RefreshCw, ShoppingBag, CheckCircle, Clock, TrendingUp } from 'lucide-react'
import StatCard from '@/components/StatCard'
import Link from 'next/link'

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendiente', accepted: 'Aceptado', preparing: 'Preparando',
  ready: 'Listo', on_the_way: 'En camino', delivered: 'Entregado',
  rejected: 'Rechazado', cancelled: 'Cancelado',
}

const STATUS_COLOR: Record<string, string> = {
  pending:    'bg-amber-500/10 text-amber-400 border-amber-500/20',
  accepted:   'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
  preparing:  'bg-blue-500/10 text-blue-400 border-blue-500/20',
  ready:      'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  on_the_way: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
  delivered:  'bg-zinc-700/50 text-zinc-400 border-zinc-700',
  rejected:   'bg-red-500/10 text-red-400 border-red-500/20',
  cancelled:  'bg-zinc-700/50 text-zinc-500 border-zinc-700',
}

const STATUS_NEXT: Record<string, string[]> = {
  pending:    ['accepted', 'rejected'],
  accepted:   ['preparing'],
  preparing:  ['ready'],
  ready:      ['on_the_way'],
  on_the_way: ['delivered'],
}

// Modal de aceptación — pide tiempo y precio
function AcceptModal({
  orderId, storeName, onClose, onConfirm
}: {
  orderId: number
  storeName: string
  onClose: () => void
  onConfirm: (minutes: number, total: number, msg: string) => void
}) {
  const [minutes, setMinutes] = useState(30)
  const [total,   setTotal]   = useState(0)
  const [msg,     setMsg]     = useState('')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-sm">
        <h3 className="text-white font-bold mb-1">Aceptar pedido</h3>
        <p className="text-zinc-500 text-xs mb-5">{storeName}</p>

        <div className="space-y-4">
          <div>
            <label className="text-zinc-400 text-xs block mb-1.5">⏱️ Tiempo de entrega (minutos)</label>
            <input
              type="number" min={10} max={120}
              value={minutes}
              onChange={e => setMinutes(+e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
            />
          </div>
          <div>
            <label className="text-zinc-400 text-xs block mb-1.5">💰 Total del pedido (COP)</label>
            <input
              type="number" min={0}
              value={total}
              onChange={e => setTotal(+e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              placeholder="45000"
            />
          </div>
          <div>
            <label className="text-zinc-400 text-xs block mb-1.5">💬 Mensaje para el cliente (opcional)</label>
            <input
              type="text"
              value={msg}
              onChange={e => setMsg(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              placeholder="ej: Tu pedido incluye papas gratis hoy 🍟"
            />
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 text-sm text-zinc-400 bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-all"
          >
            Cancelar
          </button>
          <button
            onClick={() => onConfirm(minutes, total, msg)}
            disabled={minutes < 5}
            className="flex-1 py-2.5 text-sm text-white font-medium bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-xl transition-all"
          >
            ✅ Confirmar
          </button>
        </div>
      </div>
    </div>
  )
}

// Modal de rechazo
function RejectModal({
  orderId, onClose, onConfirm
}: {
  orderId: number
  onClose: () => void
  onConfirm: (reason: string) => void
}) {
  const [reason, setReason] = useState('')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-sm">
        <h3 className="text-white font-bold mb-1">Rechazar pedido</h3>
        <p className="text-zinc-500 text-xs mb-4">El cliente recibirá una notificación.</p>
        <label className="text-zinc-400 text-xs block mb-1.5">Motivo (recomendado)</label>
        <input
          type="text"
          value={reason}
          onChange={e => setReason(e.target.value)}
          className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-red-500"
          placeholder="ej: Sin disponibilidad, cerrado por mantenimiento..."
        />
        <div className="flex gap-3 mt-5">
          <button onClick={onClose} className="flex-1 py-2.5 text-sm text-zinc-400 bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-all">
            Cancelar
          </button>
          <button
            onClick={() => onConfirm(reason)}
            className="flex-1 py-2.5 text-sm text-white font-medium bg-red-600 hover:bg-red-500 rounded-xl transition-all"
          >
            ❌ Rechazar
          </button>
        </div>
      </div>
    </div>
  )
}

export default function DomiciliosPage() {
  const [orders, setOrders]     = useState<any[]>([])
  const [stats,  setStats]      = useState<OrderStats | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [acceptModal, setAcceptModal] = useState<{ orderId: number; storeName: string } | null>(null)
  const [rejectModal, setRejectModal] = useState<{ orderId: number } | null>(null)

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true)
    try {
      const [o, s] = await Promise.all([getOrders(), getOrderStats()])
      setOrders(Array.isArray(o) ? o : [])
      setStats(s)
    } catch (e) { console.error(e) }
    finally { setRefreshing(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const t = setInterval(() => load(true), 20_000)
    return () => clearInterval(t)
  }, [load])

  const handleAccept = async (orderId: number, minutes: number, total: number, msg: string) => {
    await updateOrderStatus(orderId, 'accepted', '', minutes, total, msg)
    setAcceptModal(null)
    load(true)
  }

  const handleReject = async (orderId: number, reason: string) => {
    await updateOrderStatus(orderId, 'rejected', reason)
    setRejectModal(null)
    load(true)
  }

  const handleSimpleStatus = async (orderId: number, status: string) => {
    await updateOrderStatus(orderId, status)
    load(true)
  }

  const pendingCount = orders.filter(o => o.status === 'pending').length

  return (
    <div className="p-6 space-y-6">
      {acceptModal && (
        <AcceptModal
          orderId={acceptModal.orderId}
          storeName={acceptModal.storeName}
          onClose={() => setAcceptModal(null)}
          onConfirm={(m, t, msg) => handleAccept(acceptModal.orderId, m, t, msg)}
        />
      )}
      {rejectModal && (
        <RejectModal
          orderId={rejectModal.orderId}
          onClose={() => setRejectModal(null)}
          onConfirm={(r) => handleReject(rejectModal.orderId, r)}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Domicilios</h1>
          <p className="text-zinc-400 text-sm mt-1">Pedidos activos de todos los locales</p>
        </div>
        <div className="flex items-center gap-2">
          {pendingCount > 0 && (
            <span className="px-3 py-1.5 bg-amber-500/10 text-amber-400 text-xs font-semibold rounded-full border border-amber-500/20 animate-pulse">
              {pendingCount} pendiente{pendingCount > 1 ? 's' : ''}
            </span>
          )}
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="p-2 text-zinc-400 hover:text-white bg-zinc-800 rounded-lg transition-all disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <StatCard title="Pedidos hoy"      value={stats.total_today}     icon={<ShoppingBag size={18}/>} color="indigo" />
          <StatCard title="Entregados hoy"   value={stats.delivered_today} icon={<CheckCircle size={18}/>} color="emerald" />
          <StatCard title="Pendientes ahora" value={stats.pending_now}     icon={<Clock size={18}/>}       color="amber" />
          <StatCard title="Ingresos hoy"     value={`$${(stats.revenue_today||0).toLocaleString('es-CO')}`} icon={<TrendingUp size={18}/>} color="violet" />
        </div>
      )}

      {/* Pedidos */}
      {orders.length === 0 ? (
        <div className="text-center py-20">
          <ShoppingBag size={40} className="text-zinc-700 mx-auto mb-3" />
          <p className="text-zinc-500">Sin pedidos activos por ahora</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {orders.map(order => {
            const nextStatuses = STATUS_NEXT[order.status] || []
            const isPending    = order.status === 'pending'
            return (
              <div key={order.id} className={`bg-zinc-900 border rounded-2xl p-5 transition-all ${
                isPending ? 'border-amber-500/40 shadow-amber-500/5 shadow-lg' : 'border-zinc-800'
              }`}>
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <p className="text-white font-semibold">{order.order_number}</p>
                    <p className="text-zinc-400 text-xs">{order.client_name} · {order.client_phone}</p>
                    <p className="text-indigo-400 text-xs mt-0.5 font-medium">{order.store_name}</p>
                  </div>
                  <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${STATUS_COLOR[order.status] || 'bg-zinc-700 text-zinc-400 border-zinc-700'}`}>
                    {STATUS_LABELS[order.status]}
                  </span>
                </div>

                {order.delivery_address && (
                  <p className="text-zinc-500 text-xs mb-2">📍 {order.delivery_address}</p>
                )}
                {order.notes && (
                  <p className="text-zinc-500 text-xs mb-2">📝 {order.notes}</p>
                )}

                <div className="space-y-0.5 mb-3 pb-3 border-b border-zinc-800">
                  {(order.items || []).map((item: any, i: number) => (
                    <p key={i} className="text-zinc-300 text-xs">
                      {item.quantity}× {item.product_name}
                      {item.notes && <span className="text-zinc-600"> ({item.notes})</span>}
                    </p>
                  ))}
                </div>

                <div className="flex items-center justify-between mb-3">
                  <p className="text-white font-semibold text-sm">
                    Total: ${(order.total || 0).toLocaleString('es-CO')}
                  </p>
                  {order.delivery_time_minutes && (
                    <p className="text-zinc-500 text-xs">⏱️ {order.delivery_time_minutes} min</p>
                  )}
                </div>

                {/* Botones de acción */}
                {isPending ? (
                  <div className="flex gap-2">
                    <button
                      onClick={() => setAcceptModal({ orderId: order.id, storeName: order.store_name })}
                      className="flex-1 py-2 rounded-xl text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-all"
                    >
                      ✅ Aceptar
                    </button>
                    <button
                      onClick={() => setRejectModal({ orderId: order.id })}
                      className="flex-1 py-2 rounded-xl text-xs font-medium bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20 transition-all"
                    >
                      ❌ Rechazar
                    </button>
                  </div>
                ) : nextStatuses.length > 0 ? (
                  <div className="flex gap-2">
                    {nextStatuses.map(ns => (
                      <button
                        key={ns}
                        onClick={() => handleSimpleStatus(order.id, ns)}
                        className="flex-1 py-2 rounded-xl text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-all"
                      >
                        → {STATUS_LABELS[ns]}
                      </button>
                    ))}
                  </div>
                ) : null}

                {/* Enlace al micro-panel del local */}
                <div className="mt-2 text-right">
                  <Link
                    href={`/local/${encodeURIComponent(order.store_name)}`}
                    className="text-xs text-zinc-600 hover:text-indigo-400 transition-colors"
                  >
                    Ver panel del local →
                  </Link>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}