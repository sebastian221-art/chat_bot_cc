// 📄 ARCHIVO: panel/app/local/[id]/page.tsx
'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'next/navigation'
import {
  getOrdersByStore, getProducts, updateOrderStatus,
  createProduct, deleteProduct, toggleProduct,
  Product, Order, ProductPayload
} from '@/lib/api'
import { RefreshCw, Plus, Trash2, ToggleLeft, ToggleRight, ShoppingBag, UtensilsCrossed } from 'lucide-react'
import Modal from '@/components/Modal'

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendiente', accepted: 'Aceptado', preparing: 'Preparando',
  ready: 'Listo', on_the_way: 'En camino', delivered: 'Entregado',
  rejected: 'Rechazado', cancelled: 'Cancelado',
}
const STATUS_NEXT: Record<string, string[]> = {
  pending: ['accepted', 'rejected'], accepted: ['preparing'],
  preparing: ['ready'], ready: ['on_the_way'], on_the_way: ['delivered'],
}

const EMPTY_PRODUCT: ProductPayload = {
  store_name: '', name: '', description: '', price: 0,
  category: '', photo_url: '', active: true,
}

export default function LocalPage() {
  const { id } = useParams()
  const storeName = decodeURIComponent(id as string)

  const [orders, setOrders]     = useState<Order[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [tab, setTab]           = useState<'orders' | 'menu'>('orders')
  const [refreshing, setRefreshing] = useState(false)
  const [showModal, setShowModal]   = useState(false)
  const [newProduct, setNewProduct] = useState<ProductPayload>({ ...EMPTY_PRODUCT, store_name: storeName })
  const [saving, setSaving]         = useState(false)

  const load = useCallback(async (silent = false) => {
    if (!silent) {}
    else setRefreshing(true)
    try {
      const [o, p] = await Promise.all([
        getOrdersByStore(storeName),
        getProducts(storeName),
      ])
      setOrders(o)
      setProducts(p)
    } catch (e) { console.error(e) }
    finally { setRefreshing(false) }
  }, [storeName])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const t = setInterval(() => load(true), 15_000)
    return () => clearInterval(t)
  }, [load])

  const changeStatus = async (orderId: number, status: string) => {
    await updateOrderStatus(orderId, status)
    load(true)
  }

  const saveProduct = async () => {
    setSaving(true)
    try {
      await createProduct({ ...newProduct, store_name: storeName })
      setShowModal(false)
      setNewProduct({ ...EMPTY_PRODUCT, store_name: storeName })
      load(true)
    } catch (e) { console.error(e) }
    finally { setSaving(false) }
  }

  const pendingCount = orders.filter(o => o.status === 'pending').length

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">{storeName}</h1>
          <p className="text-zinc-400 text-sm mt-1">Panel del local</p>
        </div>
        <div className="flex items-center gap-2">
          {pendingCount > 0 && (
            <span className="px-3 py-1.5 bg-amber-500/10 text-amber-400 text-xs font-semibold rounded-full border border-amber-500/20 animate-pulse">
              {pendingCount} pedido{pendingCount > 1 ? 's' : ''} nuevo{pendingCount > 1 ? 's' : ''}
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

      {/* Tabs */}
      <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded-xl p-1 w-fit">
        {(['orders', 'menu'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-xs font-medium transition-all ${
              tab === t ? 'bg-indigo-600 text-white' : 'text-zinc-400 hover:text-white'
            }`}
          >
            {t === 'orders' ? `🛵 Pedidos (${orders.length})` : `🍽️ Menú (${products.length})`}
          </button>
        ))}
      </div>

      {/* Tab pedidos */}
      {tab === 'orders' && (
        orders.length === 0 ? (
          <div className="text-center py-20">
            <ShoppingBag size={36} className="text-zinc-700 mx-auto mb-3" />
            <p className="text-zinc-500">Sin pedidos activos por ahora</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {orders.map(order => {
              const nextStatuses = STATUS_NEXT[order.status] || []
              return (
                <div key={order.id} className={`bg-zinc-900 border rounded-2xl p-5 transition-all ${
                  order.status === 'pending' ? 'border-amber-500/40 shadow-amber-500/5 shadow-lg' : 'border-zinc-800'
                }`}>
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <p className="text-white font-semibold">{order.order_number}</p>
                      <p className="text-zinc-400 text-xs">{order.client_name} — {order.client_phone}</p>
                    </div>
                    <span className="text-xs text-zinc-400 bg-zinc-800 px-2 py-1 rounded-lg">
                      {STATUS_LABELS[order.status]}
                    </span>
                  </div>

                  {order.delivery_address && (
                    <p className="text-zinc-500 text-xs mb-3">📍 {order.delivery_address}</p>
                  )}

                  <div className="space-y-1 mb-4">
                    {order.items.map((item, i) => (
                      <p key={i} className="text-xs text-zinc-300">
                        {item.quantity}× {item.product_name}
                        {item.notes && <span className="text-zinc-600"> ({item.notes})</span>}
                      </p>
                    ))}
                    <p className="text-white font-semibold text-sm pt-1">
                      Total: ${order.total.toLocaleString('es-CO')}
                    </p>
                  </div>

                  {nextStatuses.length > 0 && (
                    <div className="flex gap-2">
                      {nextStatuses.map(ns => (
                        <button
                          key={ns}
                          onClick={() => changeStatus(order.id, ns)}
                          className={`flex-1 py-2 rounded-xl text-xs font-medium transition-all ${
                            ns === 'rejected'
                              ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20'
                              : 'bg-indigo-600 hover:bg-indigo-500 text-white'
                          }`}
                        >
                          → {STATUS_LABELS[ns]}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )
      )}

      {/* Tab menú */}
      {tab === 'menu' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button
              onClick={() => setShowModal(true)}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium px-4 py-2.5 rounded-xl transition-all"
            >
              <Plus size={14} /> Agregar producto
            </button>
          </div>

          {products.length === 0 ? (
            <div className="text-center py-20">
              <UtensilsCrossed size={36} className="text-zinc-700 mx-auto mb-3" />
              <p className="text-zinc-500">El menú está vacío</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
              {products.map(p => (
                <div key={p.id} className={`bg-zinc-900 border rounded-2xl p-4 transition-all ${
                  p.active ? 'border-zinc-800' : 'border-zinc-800 opacity-50'
                }`}>
                  {p.category && (
                    <p className="text-indigo-400 text-xs mb-2">{p.category}</p>
                  )}
                  <p className="text-white font-semibold">{p.name}</p>
                  {p.description && (
                    <p className="text-zinc-500 text-xs mt-1 leading-relaxed">{p.description}</p>
                  )}
                  <p className="text-emerald-400 font-bold mt-2">${p.price.toLocaleString('es-CO')}</p>
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={() => { toggleProduct(p.id); load(true) }}
                      className="flex-1 flex items-center justify-center gap-1.5 text-xs text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 py-1.5 rounded-lg transition-all"
                    >
                      {p.active ? <ToggleRight size={13} className="text-emerald-400" /> : <ToggleLeft size={13} />}
                      {p.active ? 'Activo' : 'Inactivo'}
                    </button>
                    <button
                      onClick={() => { deleteProduct(p.id); load(true) }}
                      className="p-1.5 text-zinc-600 hover:text-red-400 bg-zinc-800 hover:bg-red-500/10 rounded-lg transition-all"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Modal nuevo producto */}
      <Modal open={showModal} onClose={() => setShowModal(false)} title="Agregar producto">
        <div className="space-y-3">
          {[
            { key: 'name',        label: 'Nombre',      type: 'text' },
            { key: 'price',       label: 'Precio (COP)',type: 'number' },
            { key: 'category',    label: 'Categoría',   type: 'text' },
            { key: 'description', label: 'Descripción', type: 'text' },
          ].map(({ key, label, type }) => (
            <div key={key}>
              <label className="text-zinc-400 text-xs block mb-1">{label}</label>
              <input
                type={type}
                value={(newProduct as any)[key]}
                onChange={e => setNewProduct(p => ({ ...p, [key]: type === 'number' ? +e.target.value : e.target.value }))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              />
            </div>
          ))}
          <button
            onClick={saveProduct}
            disabled={saving || !newProduct.name || !newProduct.price}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl transition-all text-sm"
          >
            {saving ? 'Guardando...' : 'Agregar producto'}
          </button>
        </div>
      </Modal>
    </div>
  )
}