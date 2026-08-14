// 📄 ARCHIVO: panel/app/tiendas/page.tsx
'use client'
import { useEffect, useState, useRef } from 'react'
import { getStores, createStore, updateStore, deleteStore, exportStores, importStores, StorePayload } from '@/lib/api'
import Modal from '@/components/Modal'
import ImageUpload from '@/components/ImageUpload'
import { Plus, Pencil, Trash2, Search, RefreshCw, Store, Download, Upload, ImageOff, MapPin, Phone, Clock } from 'lucide-react'

const CATEGORIES = [
  'Ropa y Calzado','Ropa y Moda','Ropa Mujer','Ropa y Calzado Deportivo',
  'Accesorios y Maletas','Tecnología','Tienda por Departamentos',
  'Comida Rápida','Restaurante','Cafetería','Supermercado',
  'Farmacia y Salud','Salud y Óptica','Telecomunicaciones',
  'Librería y Papelería','Gimnasio y Wellness','Entretenimiento','Otro',
]

const FLOORS = ['Sótano','Piso 1','Piso 2','Piso 3','Piso 1 y Piso 2']

const EMPTY: StorePayload = {
  name:'', local_number:'', floor:'Piso 1', category:'', description:'',
  schedule:'', phone:'', location_hint:'', tags:'', photo_url:'', extra_info:'',
}

export default function TiendasPage() {
  const [stores, setStores]     = useState<(StorePayload & { _idx: number })[]>([])
  const [loading, setLoading]   = useState(true)
  const [search, setSearch]     = useState('')
  const [modal, setModal]       = useState(false)
  const [editing, setEditing]   = useState<number | null>(null)
  const [form, setForm]         = useState<StorePayload>(EMPTY)
  const [saving, setSaving]     = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)
  const [importing, setImporting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await getStores()
      setStores(data.map((s: StorePayload) => ({ ...s, _idx: s.id! })))
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    try {
      const result = await importStores(file)
      alert(`Importación completa:\n✅ ${result.created} locales nuevos\n🔄 ${result.updated} actualizados\n⏭️ ${result.skipped} saltados${result.errors?.length ? '\n\nAvisos:\n' + result.errors.join('\n') : ''}`)
      await load()
    } catch (err: any) {
      alert('Error al importar: ' + err.message)
    } finally {
      setImporting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const filtered = stores.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.category.toLowerCase().includes(search.toLowerCase()) ||
    s.floor.toLowerCase().includes(search.toLowerCase()) ||
    (s.local_number || '').toLowerCase().includes(search.toLowerCase())
  )

  const openNew = () => { setForm(EMPTY); setEditing(null); setModal(true) }
  const openEdit = (s: StorePayload & { _idx: number }) => {
    const { _idx, ...rest } = s
    setForm({ ...EMPTY, ...rest }); setEditing(_idx); setModal(true)
  }
  const closeModal = () => setModal(false)

  const handleSave = async () => {
    if (!form.name || !form.category) return alert('Nombre y categoría son requeridos')
    setSaving(true)
    try {
      if (editing !== null) await updateStore(editing, form)
      else                  await createStore(form)
      await load()
      closeModal()
    } catch (e: any) { alert('Error: ' + e.message) }
    finally { setSaving(false) }
  }

  const handleDelete = async (idx: number, name: string) => {
    if (!confirm(`¿Eliminar "${name}"? Esta acción no se puede deshacer.`)) return
    setDeleting(idx)
    try { await deleteStore(idx); await load() }
    catch (e: any) { alert('Error: ' + e.message) }
    finally { setDeleting(null) }
  }

  const field = (key: keyof StorePayload) => ({
    value: form[key] as string,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm(p => ({ ...p, [key]: e.target.value })),
  })

  return (
    <div className="p-8">

      {/* Header */}
      <div className="flex items-center justify-between mb-7">
        <div>
          <h1 className="text-2xl font-bold text-white">Locales</h1>
          <p className="text-zinc-500 text-sm mt-0.5">{stores.length} locales en el directorio</p>
        </div>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleImportFile}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className="flex items-center gap-2 text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-sm font-medium px-3 py-2 rounded-lg transition-all"
          >
            <Upload size={14} /> {importing ? 'Importando...' : 'Importar CSV'}
          </button>
          <button
            onClick={() => exportStores()}
            className="flex items-center gap-2 text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 text-sm font-medium px-3 py-2 rounded-lg transition-all"
          >
            <Download size={14} /> Exportar CSV
          </button>
          <button
            onClick={load}
            className="p-2 text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-all"
          >
            <RefreshCw size={14} />
          </button>
          <button
            onClick={openNew}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium px-4 py-2 rounded-xl transition-all"
          >
            <Plus size={14} /> Nuevo local
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-6">
        <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" />
        <input
          className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-indigo-500"
          placeholder="Buscar por nombre, local, categoría o piso..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {/* Grid de tarjetas */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-64 bg-zinc-900 border border-zinc-800 rounded-2xl animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-20 text-center bg-zinc-900 border border-zinc-800 rounded-2xl">
          <Store size={32} className="text-zinc-700 mx-auto mb-3" />
          <p className="text-zinc-500 text-sm">{search ? 'Sin resultados para esa búsqueda' : '¡Agrega el primer local!'}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map(s => (
            <div
              key={s._idx}
              className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden hover:border-zinc-700 transition-all flex flex-col"
            >
              {/* Foto o placeholder */}
              <div className="h-36 bg-zinc-950 relative flex-shrink-0">
                {s.photo_url ? (
                  <img
                    src={s.photo_url}
                    alt={s.name}
                    className="w-full h-full object-cover"
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <ImageOff size={22} className="text-zinc-700" />
                  </div>
                )}
                <span className="absolute top-2 left-2 text-[10px] font-mono font-bold bg-black/70 text-white px-2 py-1 rounded-lg backdrop-blur-sm">
                  {s.local_number || 'S/N'}
                </span>
                <div className="absolute top-2 right-2 flex gap-1.5">
                  <button
                    onClick={() => openEdit(s)}
                    className="p-1.5 bg-black/70 hover:bg-black text-zinc-300 hover:text-white rounded-lg backdrop-blur-sm transition-all"
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    onClick={() => handleDelete(s._idx, s.name)}
                    disabled={deleting === s._idx}
                    className="p-1.5 bg-black/70 hover:bg-red-900 text-zinc-300 hover:text-red-300 rounded-lg backdrop-blur-sm transition-all disabled:opacity-40"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>

              {/* Info */}
              <div className="p-4 flex-1 flex flex-col">
                <h3 className="text-white font-semibold text-sm leading-tight mb-1.5">{s.name}</h3>
                <div className="flex flex-wrap gap-1.5 mb-2.5">
                  <span className="text-[10px] text-indigo-400 bg-indigo-400/10 px-2 py-0.5 rounded-full">{s.floor}</span>
                  <span className="text-[10px] text-zinc-400 bg-zinc-800 px-2 py-0.5 rounded-full truncate max-w-[140px]">{s.category}</span>
                </div>
                {s.description && (
                  <p className="text-zinc-500 text-xs leading-relaxed line-clamp-2 mb-2.5">{s.description}</p>
                )}
                <div className="mt-auto pt-2 border-t border-zinc-800/60 space-y-1">
                  {s.schedule && (
                    <p className="text-zinc-600 text-[11px] flex items-center gap-1.5 truncate">
                      <Clock size={10} className="flex-shrink-0" /> {s.schedule}
                    </p>
                  )}
                  {s.phone && (
                    <p className="text-zinc-600 text-[11px] flex items-center gap-1.5">
                      <Phone size={10} className="flex-shrink-0" /> {s.phone}
                    </p>
                  )}
                  {s.location_hint && (
                    <p className="text-zinc-600 text-[11px] flex items-center gap-1.5 truncate">
                      <MapPin size={10} className="flex-shrink-0" /> {s.location_hint}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      <Modal
        open={modal}
        title={editing !== null ? 'Editar local' : 'Nuevo local'}
        onClose={closeModal}
        size="lg"
      >
        <div className="grid grid-cols-2 gap-4">

          <div className="col-span-2">
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Nombre *</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" placeholder="ej: Nike Store" {...field('name')} />
          </div>

          <div className="col-span-2">
            <ImageUpload
              value={form.photo_url}
              onChange={url => setForm(p => ({ ...p, photo_url: url }))}
              label="Foto del local"
              accent="indigo"
            />
          </div>

          <div className="col-span-2">
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">
              Información adicional <span className="text-zinc-600 font-normal">(carta, cartelera, promociones — lo que aplique a este local)</span>
            </label>
            <textarea
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 resize-none h-24"
              placeholder="ej: Carta del restaurante, cartelera de películas de la semana, promociones vigentes..."
              {...field('extra_info')}
            />
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Número de local</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" placeholder="ej: 104" {...field('local_number')} />
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Piso *</label>
            <select className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" {...field('floor')}>
              {FLOORS.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Categoría *</label>
            <select className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" {...field('category')}>
              <option value="">Seleccionar...</option>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div className="col-span-2">
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Descripción</label>
            <textarea className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 resize-none h-20" placeholder="Qué vende, productos destacados..." {...field('description')} />
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Horario</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" placeholder="Lun-Sab 10am-8pm" {...field('schedule')} />
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Teléfono</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" placeholder="607 123 4567" {...field('phone')} />
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Ubicación exacta</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" placeholder="Piso 1, ala norte, frente a la entrada" {...field('location_hint')} />
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Tags (coma separados)</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" placeholder="nike,zapatillas,deportivo" {...field('tags')} />
          </div>

        </div>

        <div className="flex gap-3 justify-end mt-6 pt-5 border-t border-zinc-800">
          <button onClick={closeModal} className="px-4 py-2 text-sm text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-all">
            Cancelar
          </button>
          <button onClick={handleSave} disabled={saving} className="px-4 py-2 text-sm text-white font-medium bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-xl transition-all">
            {saving ? 'Guardando...' : editing !== null ? 'Guardar cambios' : 'Crear local'}
          </button>
        </div>
      </Modal>

    </div>
  )
}