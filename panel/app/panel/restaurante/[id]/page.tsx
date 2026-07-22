// 📄 ARCHIVO: panel/app/panel/restaurante/[id]/page.tsx
'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'next/navigation'
import {
  getOrdersByStore, getProducts, updateOrderStatus,
  createProduct, deleteProduct, toggleProduct,
  type Product, type Order, type ProductPayload
} from '@/lib/api'
import { RefreshCw, Plus, Trash2, ToggleLeft, ToggleRight,
         ShoppingBag, UtensilsCrossed, Power, Clock, X, Check,
         MessageSquare, AlertCircle } from 'lucide-react'
import Modal from '@/components/Modal'

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendiente', accepted: 'Aceptado', preparing: 'Preparando',
  ready: 'Listo', on_the_way: 'En camino', delivered: 'Entregado',
  rejected: 'Rechazado', cancelled: 'Cancelado',
}
// Estados que avanza con un solo click (sin modal)
const STATUS_NEXT_SIMPLE: Record<string, string[]> = {
  accepted: ['preparing'],
  preparing: ['ready'],
  ready: ['on_the_way'],
  on_the_way: ['delivered'],
}
const EMPTY: ProductPayload = { store_name: '', name: '', description: '', price: 0, category: '', photo_url: '', active: true }

export default function RestaurantePage() {
  const { id } = useParams<{ id: string }>()
  const storeName = decodeURIComponent(id)

  const [orders,    setOrders]    = useState<Order[]>([])
  const [products,  setProducts]  = useState<Product[]>([])
  const [tab,       setTab]       = useState<'orders' | 'menu' | 'info'>('orders')
  const [isOpen,    setIsOpen]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [showModal,  setShowModal]  = useState(false)
  const [newProduct, setNewProduct] = useState<ProductPayload>({ ...EMPTY, store_name: storeName })
  const [saving,     setSaving]     = useState(false)

  // ── Modal Aceptar ─────────────────────────────────────────────
  const [acceptOrder, setAcceptOrder] = useState<Order | null>(null)
  const [acceptTime,  setAcceptTime]  = useState('30')
  const [acceptMsg,   setAcceptMsg]   = useState('')
  const [acceptTotal, setAcceptTotal] = useState('')
  const [accepting,   setAccepting]   = useState(false)

  // ── Modal Rechazar ────────────────────────────────────────────
  const [rejectOrder,  setRejectOrder]  = useState<Order | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [rejecting,    setRejecting]    = useState(false)

  const pendingCount = orders.filter(o => o.status === 'pending').length

  const load = useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true)
    try {
      const [o, p] = await Promise.all([getOrdersByStore(storeName), getProducts(storeName)])
      setOrders(o); setProducts(p)
    } finally { setRefreshing(false) }
  }, [storeName])

  useEffect(() => { load() }, [load])
  // Auto-refresh cada 30s
  useEffect(() => {
    const t = setInterval(() => load(true), 30_000)
    return () => clearInterval(t)
  }, [load])

  // ── Aceptar pedido ────────────────────────────────────────────
  function openAccept(order: Order) {
    setAcceptOrder(order)
    setAcceptTime('30')
    setAcceptMsg('')
    setAcceptTotal(order.total?.toString() || '')
  }

  async function confirmAccept() {
    if (!acceptOrder) return
    setAccepting(true)
    try {
      await updateOrderStatus(
        acceptOrder.id, 'accepted', '',
        parseInt(acceptTime) || 30,
        acceptTotal ? parseFloat(acceptTotal) : undefined,
        acceptMsg.trim() || undefined,
      )
      setAcceptOrder(null)
      load(true)
    } catch (e) { alert('Error al aceptar el pedido') }
    finally { setAccepting(false) }
  }

  // ── Rechazar pedido ───────────────────────────────────────────
  function openReject(order: Order) {
    setRejectOrder(order); setRejectReason('')
  }

  async function confirmReject() {
    if (!rejectOrder) return
    setRejecting(true)
    try {
      await updateOrderStatus(rejectOrder.id, 'rejected', rejectReason.trim() || 'Sin disponibilidad')
      setRejectOrder(null); load(true)
    } catch (e) { alert('Error al rechazar el pedido') }
    finally { setRejecting(false) }
  }

  // ── Cambiar estado simple (sin modal) ─────────────────────────
  async function changeStatusSimple(orderId: number, newStatus: string) {
    await updateOrderStatus(orderId, newStatus)
    load(true)
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">

      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-white font-bold text-xl">{storeName}</h1>
          <p className="text-zinc-500 text-sm mt-0.5">Panel Restaurante</p>
        </div>
        <div className="flex items-center gap-2">
          {pendingCount > 0 && (
            <span className="px-3 py-1.5 bg-amber-500/10 text-amber-400 text-xs font-semibold rounded-full border border-amber-500/20 animate-pulse">
              {pendingCount} nuevo{pendingCount > 1 ? 's' : ''}
            </span>
          )}
          <button onClick={() => setIsOpen(v => !v)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
              isOpen ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'
            }`}>
            <Power size={12} /> {isOpen ? 'Abierto' : 'Cerrado'}
          </button>
          <button onClick={() => load(true)} disabled={refreshing}
            className="p-2 text-zinc-400 hover:text-white bg-zinc-800 rounded-lg transition-all disabled:opacity-50">
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded-xl p-1 w-fit">
        {(['orders', 'menu', 'info'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-xs font-medium transition-all ${tab === t ? 'bg-indigo-600 text-white' : 'text-zinc-400 hover:text-white'}`}>
            {t === 'orders' ? `🛵 Pedidos (${orders.length})` : t === 'menu' ? `🍽️ Menú (${products.length})` : '⚙️ Horarios'}
          </button>
        ))}
      </div>

      {/* ── Tab: Pedidos ─────────────────────────────────────── */}
      {tab === 'orders' && (
        orders.length === 0
          ? <div className="text-center py-20"><ShoppingBag size={36} className="text-zinc-700 mx-auto mb-3" /><p className="text-zinc-500 text-sm">Sin pedidos activos</p></div>
          : <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {orders.map(order => {
                const simpleNext = STATUS_NEXT_SIMPLE[order.status] || []
                return (
                  <div key={order.id} className={`bg-zinc-900 border rounded-2xl p-5 ${order.status === 'pending' ? 'border-amber-500/40' : 'border-zinc-800'}`}>
                    {/* Cabecera del pedido */}
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <p className="text-white font-semibold">{order.order_number}</p>
                        <p className="text-zinc-400 text-xs">{order.client_name} · {order.client_phone}</p>
                      </div>
                      <span className="text-xs text-zinc-400 bg-zinc-800 px-2 py-1 rounded-lg">{STATUS_LABELS[order.status]}</span>
                    </div>

                    {order.delivery_address && (
                      <p className="text-zinc-500 text-xs mb-2">📍 {order.delivery_address}</p>
                    )}
                    {order.notes && (
                      <p className="text-amber-400/80 text-xs mb-2 bg-amber-500/5 border border-amber-500/10 px-2 py-1 rounded-lg">
                        💬 {order.notes}
                      </p>
                    )}
                    {order.payment_method && (
                      <p className="text-zinc-500 text-xs mb-2">💳 {order.payment_method}</p>
                    )}

                    {/* Items */}
                    <div className="space-y-0.5 mb-3 pb-3 border-b border-zinc-800">
                      {order.items?.map((item, i) => (
                        <p key={i} className="text-zinc-300 text-xs">{item.quantity}× {item.product_name}</p>
                      ))}
                      <p className="text-white font-semibold text-sm pt-1">
                        Total: ${order.total?.toLocaleString('es-CO')}
                      </p>
                    </div>

                    {/* Info de aceptación (si ya fue aceptado) */}
                    {order.delivery_time_minutes && (
                      <p className="text-emerald-400 text-xs mb-2 flex items-center gap-1">
                        <Clock size={11} /> {order.delivery_time_minutes} min estimados
                      </p>
                    )}
                    {order.store_message && (
                      <p className="text-zinc-400 text-xs mb-2 italic">"{order.store_message}"</p>
                    )}

                    {/* Acciones */}
                    <div className="flex gap-2 mt-1">
                      {/* Pedido pendiente → modal de aceptar/rechazar */}
                      {order.status === 'pending' && (
                        <>
                          <button onClick={() => openAccept(order)}
                            className="flex-1 py-2.5 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-all">
                            ✅ Aceptar pedido
                          </button>
                          <button onClick={() => openReject(order)}
                            className="flex-1 py-2.5 rounded-xl text-xs font-semibold bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-all">
                            ✗ Rechazar
                          </button>
                        </>
                      )}
                      {/* Estados siguientes simples */}
                      {simpleNext.map(ns => (
                        <button key={ns} onClick={() => changeStatusSimple(order.id, ns)}
                          className="flex-1 py-2.5 rounded-xl text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-all">
                          → {STATUS_LABELS[ns]}
                        </button>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
      )}

      {/* ── Tab: Menú ────────────────────────────────────────── */}
      {tab === 'menu' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button onClick={() => setShowModal(true)}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium px-4 py-2.5 rounded-xl transition-all">
              <Plus size={14} /> Agregar producto
            </button>
          </div>
          {products.length === 0
            ? <div className="text-center py-16"><UtensilsCrossed size={32} className="text-zinc-700 mx-auto mb-3" /><p className="text-zinc-500 text-sm">Sin productos. Agrega el primero.</p></div>
            : <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {products.map(p => (
                  <div key={p.id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex justify-between items-center">
                    <div>
                      <p className={`text-sm font-medium ${p.active ? 'text-white' : 'text-zinc-500 line-through'}`}>{p.name}</p>
                      <p className="text-zinc-500 text-xs">{p.category}</p>
                      <p className="text-indigo-400 text-xs font-semibold mt-0.5">${p.price.toLocaleString('es-CO')}</p>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={async () => { await toggleProduct(p.id); load(true) }} className="p-1.5 text-zinc-400 hover:text-white">
                        {p.active ? <ToggleRight size={18} className="text-emerald-400" /> : <ToggleLeft size={18} />}
                      </button>
                      <button onClick={async () => { if (confirm('¿Eliminar?')) { await deleteProduct(p.id); load(true) } }} className="p-1.5 text-zinc-600 hover:text-red-400">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
          }
        </div>
      )}

      {/* ── Tab: Info ────────────────────────────────────────── */}
      {tab === 'info' && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 max-w-md">
          <h3 className="text-white font-semibold mb-4">Estado del local</h3>
          <div className="flex items-center justify-between">
            <span className="text-zinc-400 text-sm">Aceptar domicilios ahora</span>
            <button onClick={() => setIsOpen(v => !v)}
              className={`px-4 py-2 rounded-xl text-xs font-semibold border transition-all ${isOpen ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
              {isOpen ? '🟢 Abierto' : '🔴 Cerrado'}
            </button>
          </div>
        </div>
      )}

      {/* ══ Modal: Agregar producto ══════════════════════════════ */}
      <Modal open={showModal} onClose={() => setShowModal(false)} title="Agregar producto">
        <div className="space-y-3">
          {(['name', 'description', 'category', 'photo_url'] as const).map(f => (
            <div key={f}>
              <label className="block text-zinc-400 text-xs mb-1 capitalize">{f.replace('_', ' ')}</label>
              <input value={(newProduct as Record<string,unknown>)[f] as string || ''}
                onChange={e => setNewProduct(p => ({ ...p, [f]: e.target.value }))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white outline-none" />
            </div>
          ))}
          <div>
            <label className="block text-zinc-400 text-xs mb-1">Precio *</label>
            <input type="number" value={newProduct.price}
              onChange={e => setNewProduct(p => ({ ...p, price: parseFloat(e.target.value) || 0 }))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white outline-none" />
          </div>
          <button disabled={saving} onClick={async () => {
            setSaving(true)
            await createProduct({ ...newProduct, store_name: storeName })
            setShowModal(false); setNewProduct({ ...EMPTY, store_name: storeName }); load(true); setSaving(false)
          }} className="w-full bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium py-2 rounded-xl transition-all disabled:opacity-50">
            {saving ? 'Guardando...' : 'Guardar producto'}
          </button>
        </div>
      </Modal>

      {/* ══ Modal: Aceptar pedido ════════════════════════════════ */}
      {acceptOrder && (
        <div style={overlay} onClick={e => e.target === e.currentTarget && !accepting && setAcceptOrder(null)}>
          <div style={modalStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ color: '#fff', fontWeight: 700, fontSize: 16, margin: 0 }}>
                ✅ Aceptar pedido · {acceptOrder.order_number}
              </h3>
              {!accepting && (
                <button onClick={() => setAcceptOrder(null)} style={xBtn}><X size={16} /></button>
              )}
            </div>

            {/* Resumen del pedido */}
            <div style={{ background: '#09090b', borderRadius: 10, padding: '12px 14px', marginBottom: 16 }}>
              <p style={{ color: '#a1a1aa', fontSize: 12, marginBottom: 6 }}>📋 {acceptOrder.client_name} · {acceptOrder.client_phone}</p>
              {acceptOrder.items?.map((item, i) => (
                <p key={i} style={{ color: '#e4e4e7', fontSize: 13 }}>{item.quantity}× {item.product_name}</p>
              ))}
              {acceptOrder.notes && <p style={{ color: '#fbbf24', fontSize: 12, marginTop: 6 }}>💬 {acceptOrder.notes}</p>}
            </div>

            {/* Campos del modal */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

              <div>
                <label style={label}>⏱️ Tiempo estimado de entrega (minutos)</label>
                <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                  {['15', '20', '30', '45', '60'].map(t => (
                    <button key={t} onClick={() => setAcceptTime(t)}
                      style={{ flex: 1, padding: '7px 0', borderRadius: 8, border: `1px solid ${acceptTime === t ? '#6366f1' : '#27272a'}`,
                        background: acceptTime === t ? '#6366f1' : 'transparent', color: acceptTime === t ? '#fff' : '#71717a',
                        fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                      {t}
                    </button>
                  ))}
                  <input type="number" value={acceptTime} onChange={e => setAcceptTime(e.target.value)}
                    style={{ ...inputS, width: 60, textAlign: 'center' }} placeholder="Otro" />
                </div>
              </div>

              <div>
                <label style={label}>💰 Total del pedido (opcional, si cambia)</label>
                <input type="number" value={acceptTotal}
                  onChange={e => setAcceptTotal(e.target.value)}
                  placeholder={`$${acceptOrder.total?.toLocaleString('es-CO') || '0'}`}
                  style={inputS} />
              </div>

              <div>
                <label style={label}>💬 Mensaje al cliente (opcional)</label>
                <textarea value={acceptMsg} onChange={e => setAcceptMsg(e.target.value)}
                  placeholder="ej: ¡Todo listo! Incluimos salsa de cortesía. Tu pedido estará en 30 minutos."
                  rows={3}
                  style={{ ...inputS, resize: 'vertical', fontFamily: 'inherit' }} />
                <p style={{ color: '#52525b', fontSize: 11, marginTop: 4 }}>
                  El cliente recibe por WhatsApp: tiempo estimado + este mensaje
                </p>
              </div>

              <div style={{ display: 'flex', gap: 10 }}>
                <button onClick={() => setAcceptOrder(null)} disabled={accepting}
                  style={{ flex: 1, padding: '10px', borderRadius: 10, border: '1px solid #27272a', background: 'transparent', color: '#a1a1aa', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                  Cancelar
                </button>
                <button onClick={confirmAccept} disabled={accepting}
                  style={{ flex: 2, padding: '10px', borderRadius: 10, border: 'none', background: '#6366f1', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <Check size={15} />
                  {accepting ? 'Aceptando...' : 'Confirmar y notificar al cliente'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══ Modal: Rechazar pedido ═══════════════════════════════ */}
      {rejectOrder && (
        <div style={overlay} onClick={e => e.target === e.currentTarget && !rejecting && setRejectOrder(null)}>
          <div style={{ ...modalStyle, maxWidth: 420 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ color: '#fff', fontWeight: 700, fontSize: 16, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                <AlertCircle size={16} style={{ color: '#f87171' }} />
                Rechazar · {rejectOrder.order_number}
              </h3>
              {!rejecting && <button onClick={() => setRejectOrder(null)} style={xBtn}><X size={16} /></button>}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label style={label}>Motivo del rechazo</label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                  {['Sin disponibilidad', 'Local cerrado', 'Producto agotado', 'Dirección muy lejos'].map(r => (
                    <button key={r} onClick={() => setRejectReason(r)}
                      style={{ padding: '8px 12px', borderRadius: 8, border: `1px solid ${rejectReason === r ? '#f87171' : '#27272a'}`,
                        background: rejectReason === r ? '#7f1d1d33' : 'transparent', color: rejectReason === r ? '#f87171' : '#71717a',
                        fontSize: 13, cursor: 'pointer', textAlign: 'left' }}>
                      {r}
                    </button>
                  ))}
                  <input value={rejectReason} onChange={e => setRejectReason(e.target.value)}
                    placeholder="Otro motivo..." style={inputS} />
                </div>
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
                <button onClick={() => setRejectOrder(null)} disabled={rejecting}
                  style={{ flex: 1, padding: '10px', borderRadius: 10, border: '1px solid #27272a', background: 'transparent', color: '#a1a1aa', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                  Cancelar
                </button>
                <button onClick={confirmReject} disabled={rejecting}
                  style={{ flex: 1, padding: '10px', borderRadius: 10, border: 'none', background: '#dc2626', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>
                  {rejecting ? 'Rechazando...' : 'Rechazar pedido'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── estilos inline ───────────────────────────────────────────────
const overlay:     React.CSSProperties = { position: 'fixed', inset: 0, background: '#000000aa', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 24 }
const modalStyle:  React.CSSProperties = { background: '#18181b', border: '1px solid #27272a', borderRadius: 16, padding: 28, width: '100%', maxWidth: 520, maxHeight: '90vh', overflowY: 'auto' }
const inputS:      React.CSSProperties = { width: '100%', padding: '9px 12px', background: '#09090b', border: '1px solid #27272a', borderRadius: 8, color: '#fff', fontSize: 13, outline: 'none', boxSizing: 'border-box' }
const label:       React.CSSProperties = { color: '#a1a1aa', fontSize: 12, fontWeight: 600 }
const xBtn:        React.CSSProperties = { background: 'none', border: 'none', color: '#71717a', cursor: 'pointer', display: 'flex', alignItems: 'center' }