// 📄 ARCHIVO: panel/app/panel/tienda/[id]/page.tsx
'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { getProducts, createProduct, deleteProduct, toggleProduct, Product, ProductPayload } from '@/lib/api'
import { RefreshCw, Plus, Trash2, ToggleLeft, ToggleRight, Shirt, Tag, Package } from 'lucide-react'
import Modal from '@/components/Modal'

const EMPTY: ProductPayload = { store_name:'', name:'', description:'', price:0, category:'', photo_url:'', active:true }
const CATEGORIES = ['Camisetas','Pantalones','Vestidos','Chaquetas','Zapatos','Accesorios','Ropa deportiva','Bolsos','Otros']

export default function TiendaPage() {
  const { id } = useParams()
  const storeName = decodeURIComponent(id as string)
  const [products, setProducts] = useState<Product[]>([])
  const [tab,      setTab]      = useState<'catalogo'|'novedades'|'info'>('catalogo')
  const [refreshing, setRefreshing] = useState(false)
  const [showModal,  setShowModal]  = useState(false)
  const [newProduct, setNewProduct] = useState<ProductPayload>({ ...EMPTY, store_name: storeName })
  const [saving,     setSaving]     = useState(false)
  const [filter,     setFilter]     = useState('')

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true)
    try { setProducts(await getProducts(storeName)) }
    catch(e) { console.error(e) }
    finally { setRefreshing(false) }
  }, [storeName])

  useEffect(() => { load() }, [load])

  const filtered = products.filter(p =>
    !filter || p.category === filter
  )
  // ✅ Fix: Array.from en lugar de spread de Set
  const categories = Array.from(new Set(products.map(p => p.category).filter(Boolean))) as string[]

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">{storeName}</h1>
          <p className="text-zinc-500 text-sm mt-0.5">Panel Tienda · {products.length} productos</p>
        </div>
        <button onClick={() => load(true)} disabled={refreshing} className="p-2 text-zinc-400 hover:text-white bg-zinc-800 rounded-lg disabled:opacity-50">
          <RefreshCw size={14} className={refreshing?'animate-spin':''}/>
        </button>
      </div>

      <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded-xl p-1 w-fit">
        {(['catalogo','novedades','info'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-xs font-medium transition-all ${tab===t?'bg-indigo-600 text-white':'text-zinc-400 hover:text-white'}`}>
            {t==='catalogo'?'👗 Catálogo':t==='novedades'?'✨ Novedades':'⚙️ Info'}
          </button>
        ))}
      </div>

      {tab==='catalogo' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex gap-2 flex-wrap">
              <button onClick={() => setFilter('')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${!filter?'bg-indigo-600 text-white':'bg-zinc-800 text-zinc-400 hover:text-white'}`}>
                Todos
              </button>
              {categories.map(c => (
                <button key={c} onClick={() => setFilter(c)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${filter===c?'bg-indigo-600 text-white':'bg-zinc-800 text-zinc-400 hover:text-white'}`}>
                  {c}
                </button>
              ))}
            </div>
            <button onClick={() => setShowModal(true)} className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium px-4 py-2.5 rounded-xl">
              <Plus size={14}/> Agregar
            </button>
          </div>

          {filtered.length === 0
            ? <div className="text-center py-20"><Shirt size={36} className="text-zinc-700 mx-auto mb-3"/><p className="text-zinc-500 text-sm">Sin productos en el catálogo</p></div>
            : <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                {filtered.map(p => (
                  <div key={p.id} className={`bg-zinc-900 border rounded-2xl p-4 ${p.active?'border-zinc-800':'border-zinc-800 opacity-50'}`}>
                    {p.category && <p className="text-indigo-400 text-xs mb-1.5 flex items-center gap-1"><Tag size={10}/>{p.category}</p>}
                    <p className="text-white font-semibold text-sm">{p.name}</p>
                    {p.description && <p className="text-zinc-500 text-xs mt-1 leading-relaxed">{p.description}</p>}
                    <p className="text-emerald-400 font-bold mt-2">${p.price.toLocaleString('es-CO')}</p>
                    <div className="flex gap-2 mt-3">
                      <button onClick={() => { toggleProduct(p.id); load(true) }}
                        className="flex-1 flex items-center justify-center gap-1.5 text-xs text-zinc-400 hover:text-white bg-zinc-800 py-1.5 rounded-lg">
                        {p.active?<ToggleRight size={13} className="text-emerald-400"/>:<ToggleLeft size={13}/>}
                        {p.active?'Visible':'Oculto'}
                      </button>
                      <button onClick={() => { deleteProduct(p.id); load(true) }} className="p-1.5 text-zinc-600 hover:text-red-400 bg-zinc-800 rounded-lg">
                        <Trash2 size={13}/>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
          }
        </div>
      )}

      {tab==='novedades' && (
        <div className="space-y-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 text-center">
            <Package size={32} className="text-zinc-700 mx-auto mb-3"/>
            <p className="text-white font-semibold mb-1">Novedades y destacados</p>
            <p className="text-zinc-500 text-sm">Marca productos como novedad para que el bot los mencione cuando los clientes pregunten por tu tienda.</p>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            {products.filter(p => p.active).slice(0, 6).map(p => (
              <div key={p.id} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-white text-sm font-medium truncate">{p.name}</p>
                  <p className="text-emerald-400 text-xs">${p.price.toLocaleString('es-CO')}</p>
                </div>
                <button className="px-2.5 py-1.5 bg-zinc-800 hover:bg-indigo-600 text-zinc-400 hover:text-white text-xs rounded-lg transition-all whitespace-nowrap">
                  ✨ Destacar
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab==='info' && (
        <div className="max-w-lg space-y-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 space-y-3">
            <p className="text-white font-semibold">Información del local</p>
            {[
              { label: 'Nombre', value: storeName },
              { label: 'Categoría', value: 'Ropa y Moda' },
              { label: 'Piso', value: 'Ver en sección Tiendas' },
            ].map(f => (
              <div key={f.label} className="flex justify-between py-2 border-b border-zinc-800 last:border-0">
                <p className="text-zinc-500 text-sm">{f.label}</p>
                <p className="text-white text-sm">{f.value}</p>
              </div>
            ))}
            <p className="text-zinc-600 text-xs pt-1">Edita la info completa desde la sección <span className="text-indigo-400">Tiendas</span>.</p>
          </div>
        </div>
      )}

      <Modal open={showModal} onClose={() => setShowModal(false)} title="Agregar producto">
        <div className="space-y-3">
          {[{key:'name',label:'Nombre *',type:'text'},{key:'price',label:'Precio (COP) *',type:'number'},{key:'description',label:'Descripción',type:'text'}].map(({key,label,type}) => (
            <div key={key}>
              <label className="text-zinc-400 text-xs block mb-1">{label}</label>
              <input type={type} value={(newProduct as any)[key]} onChange={e => setNewProduct(p => ({...p,[key]:type==='number'?+e.target.value:e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"/>
            </div>
          ))}
          <div>
            <label className="text-zinc-400 text-xs block mb-1">Categoría</label>
            <select value={newProduct.category} onChange={e => setNewProduct(p => ({...p,category:e.target.value}))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500">
              <option value="">Sin categoría</option>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <button onClick={async () => { setSaving(true); await createProduct({...newProduct,store_name:storeName}); setShowModal(false); setNewProduct({...EMPTY,store_name:storeName}); load(true); setSaving(false) }}
            disabled={saving||!newProduct.name||!newProduct.price}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl text-sm">
            {saving?'Guardando...':'Agregar producto'}
          </button>
        </div>
      </Modal>
    </div>
  )
}