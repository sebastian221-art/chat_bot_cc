// 📄 ARCHIVO: panel/app/panel/farmacia/[id]/page.tsx
'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { getOrdersByStore, getProducts, updateOrderStatus, createProduct, deleteProduct, toggleProduct, Product, Order, ProductPayload } from '@/lib/api'
import { RefreshCw, Plus, Trash2, ToggleLeft, ToggleRight, Pill, ShoppingBag, AlertCircle } from 'lucide-react'
import Modal from '@/components/Modal'

const CATEGORIES = ['Medicamentos','Vitaminas y suplementos','Cuidado personal','Bebés','Primeros auxilios','Higiene','Otros']
const EMPTY: ProductPayload = { store_name:'', name:'', description:'', price:0, category:'', photo_url:'', active:true }

export default function FarmaciaPage() {
  const { id } = useParams()
  const storeName = decodeURIComponent(id as string)
  const [orders,   setOrders]   = useState<Order[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [tab,      setTab]      = useState<'pedidos'|'productos'|'alertas'>('pedidos')
  const [refreshing, setRefreshing] = useState(false)
  const [showModal,  setShowModal]  = useState(false)
  const [newProduct, setNewProduct] = useState<ProductPayload>({ ...EMPTY, store_name: storeName })
  const [saving,     setSaving]     = useState(false)

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true)
    try {
      const [o, p] = await Promise.all([getOrdersByStore(storeName), getProducts(storeName)])
      setOrders(o); setProducts(p)
    } catch(e){ console.error(e) }
    finally { setRefreshing(false) }
  }, [storeName])

  useEffect(() => { load() }, [load])
  useEffect(() => { const t = setInterval(() => load(true), 15_000); return () => clearInterval(t) }, [load])

  const pendingCount = orders.filter(o => o.status === 'pending').length

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">{storeName}</h1>
          <p className="text-zinc-500 text-sm mt-0.5">Panel Farmacia / Droguería</p>
        </div>
        <div className="flex items-center gap-2">
          {pendingCount > 0 && (
            <span className="px-3 py-1.5 bg-amber-500/10 text-amber-400 text-xs font-semibold rounded-full border border-amber-500/20 animate-pulse">
              {pendingCount} pedido{pendingCount>1?'s':''} nuevo{pendingCount>1?'s':''}
            </span>
          )}
          <button onClick={() => load(true)} disabled={refreshing} className="p-2 text-zinc-400 hover:text-white bg-zinc-800 rounded-lg disabled:opacity-50">
            <RefreshCw size={14} className={refreshing?'animate-spin':''}/>
          </button>
        </div>
      </div>

      <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded-xl p-1 w-fit">
        {(['pedidos','productos','alertas'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-xs font-medium transition-all ${tab===t?'bg-indigo-600 text-white':'text-zinc-400 hover:text-white'}`}>
            {t==='pedidos'?`🛵 Pedidos (${orders.length})`:t==='productos'?`💊 Productos (${products.length})`:'⚠️ Alertas'}
          </button>
        ))}
      </div>

      {tab==='pedidos' && (
        orders.length===0
          ? <div className="text-center py-20"><ShoppingBag size={36} className="text-zinc-700 mx-auto mb-3"/><p className="text-zinc-500 text-sm">Sin pedidos activos</p></div>
          : <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {orders.map(order => (
                <div key={order.id} className={`bg-zinc-900 border rounded-2xl p-5 ${order.status==='pending'?'border-amber-500/40':'border-zinc-800'}`}>
                  <div className="flex justify-between items-start mb-3">
                    <div><p className="text-white font-semibold">{order.order_number}</p><p className="text-zinc-400 text-xs">{order.client_name} · {order.client_phone}</p></div>
                    <span className="text-xs text-zinc-400 bg-zinc-800 px-2 py-1 rounded-lg">{order.status}</span>
                  </div>
                  {order.delivery_address && <p className="text-zinc-500 text-xs mb-2">📍 {order.delivery_address}</p>}
                  {order.items.map((item,i) => <p key={i} className="text-zinc-300 text-xs">{item.quantity}× {item.product_name}</p>)}
                  {order.status==='pending' && (
                    <div className="flex gap-2 mt-3">
                      <button onClick={() => { updateOrderStatus(order.id,'accepted'); load(true) }} className="flex-1 py-2 rounded-xl text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white">✅ Aceptar</button>
                      <button onClick={() => { updateOrderStatus(order.id,'rejected'); load(true) }} className="flex-1 py-2 rounded-xl text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20">❌ Rechazar</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
      )}

      {tab==='productos' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button onClick={() => setShowModal(true)} className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium px-4 py-2.5 rounded-xl">
              <Plus size={14}/> Agregar producto
            </button>
          </div>
          {products.length===0
            ? <div className="text-center py-20"><Pill size={36} className="text-zinc-700 mx-auto mb-3"/><p className="text-zinc-500 text-sm">Sin productos registrados</p></div>
            : <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
                {products.map(p => (
                  <div key={p.id} className={`bg-zinc-900 border rounded-2xl p-4 ${p.active?'border-zinc-800':'border-zinc-800 opacity-50'}`}>
                    {p.category && <p className="text-emerald-400 text-xs mb-1.5">{p.category}</p>}
                    <p className="text-white font-semibold text-sm">{p.name}</p>
                    {p.description && <p className="text-zinc-500 text-xs mt-1">{p.description}</p>}
                    <p className="text-emerald-400 font-bold mt-2">${p.price.toLocaleString('es-CO')}</p>
                    <div className="flex gap-2 mt-3">
                      <button onClick={() => { toggleProduct(p.id); load(true) }} className="flex-1 flex items-center justify-center gap-1.5 text-xs text-zinc-400 bg-zinc-800 py-1.5 rounded-lg">
                        {p.active?<ToggleRight size={13} className="text-emerald-400"/>:<ToggleLeft size={13}/>} {p.active?'Disponible':'Agotado'}
                      </button>
                      <button onClick={() => { deleteProduct(p.id); load(true) }} className="p-1.5 text-zinc-600 hover:text-red-400 bg-zinc-800 rounded-lg"><Trash2 size={13}/></button>
                    </div>
                  </div>
                ))}
              </div>
          }
        </div>
      )}

      {tab==='alertas' && (
        <div className="space-y-3">
          <div className="bg-amber-500/5 border border-amber-500/20 rounded-2xl p-5">
            <p className="text-amber-400 font-semibold flex items-center gap-2 mb-2"><AlertCircle size={15}/> Productos por agotarse</p>
            <p className="text-zinc-400 text-sm">Cuando los productos se marquen como inactivos (agotados) aparecerán aquí para recordarte actualizarlos.</p>
          </div>
          {products.filter(p => !p.active).length === 0
            ? <div className="text-center py-12"><p className="text-zinc-600 text-sm">✅ Todos los productos están disponibles</p></div>
            : products.filter(p => !p.active).map(p => (
                <div key={p.id} className="bg-zinc-900 border border-amber-500/20 rounded-2xl p-4 flex items-center justify-between">
                  <div><p className="text-white text-sm font-medium">{p.name}</p><p className="text-zinc-500 text-xs">{p.category}</p></div>
                  <button onClick={() => { toggleProduct(p.id); load(true) }} className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-lg">Reactivar</button>
                </div>
              ))
          }
        </div>
      )}

      <Modal open={showModal} onClose={() => setShowModal(false)} title="Agregar producto">
        <div className="space-y-3">
          {[{key:'name',label:'Nombre *',type:'text'},{key:'price',label:'Precio (COP) *',type:'number'},{key:'description',label:'Descripción / Presentación',type:'text'}].map(({key,label,type}) => (
            <div key={key}><label className="text-zinc-400 text-xs block mb-1">{label}</label>
              <input type={type} value={(newProduct as any)[key]} onChange={e => setNewProduct(p => ({...p,[key]:type==='number'?+e.target.value:e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-emerald-500"/>
            </div>
          ))}
          <div><label className="text-zinc-400 text-xs block mb-1">Categoría</label>
            <select value={newProduct.category} onChange={e => setNewProduct(p => ({...p,category:e.target.value}))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-emerald-500">
              <option value="">Sin categoría</option>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <button onClick={async () => { setSaving(true); await createProduct({...newProduct,store_name:storeName}); setShowModal(false); setNewProduct({...EMPTY,store_name:storeName}); load(true); setSaving(false) }}
            disabled={saving||!newProduct.name||!newProduct.price}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl text-sm">
            {saving?'Guardando...':'Agregar producto'}
          </button>
        </div>
      </Modal>
    </div>
  )
}