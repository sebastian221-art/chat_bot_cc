// 📄 ARCHIVO: panel/app/marketing/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { getMarketing, createMarketing, updateMarketing, deleteMarketing, getStores, MarketingPayload, StorePayload } from '@/lib/api'
import Modal from '@/components/Modal'
import EntityPhotoGallery from '@/components/EntityPhotoGallery'
import { Plus, Pencil, Trash2, RefreshCw, Megaphone } from 'lucide-react'

const EMPTY: MarketingPayload = {
  title: '', description: '', store_id: null, priority: 3, valid_until: '', active: true,
}

const PRIORITY_LABELS: Record<number, string> = {
  1: 'Baja', 2: 'Baja', 3: 'Normal', 4: 'Alta', 5: 'Máxima',
}
const PRIORITY_COLORS: Record<number, string> = {
  1: 'bg-zinc-800 text-zinc-500', 2: 'bg-zinc-800 text-zinc-500',
  3: 'bg-indigo-500/10 text-indigo-400', 4: 'bg-amber-500/10 text-amber-400',
  5: 'bg-rose-500/10 text-rose-400',
}

export default function MarketingPage() {
  const [promos, setPromos]     = useState<(MarketingPayload & { _idx: number })[]>([])
  const [stores, setStores]     = useState<StorePayload[]>([])
  const [loading, setLoading]   = useState(true)
  const [modal, setModal]       = useState(false)
  const [editing, setEditing]   = useState<number | null>(null)
  const [form, setForm]         = useState<MarketingPayload>(EMPTY)
  const [saving, setSaving]     = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const [promoData, storeData] = await Promise.all([getMarketing(), getStores()])
      setPromos(promoData.map((m: MarketingPayload) => ({ ...m, _idx: m.id! })))
      setStores(storeData)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const openNew = () => { setForm(EMPTY); setEditing(null); setModal(true) }
  const openEdit = (m: MarketingPayload & { _idx: number }) => {
    const { _idx, store_name, photos, ...rest } = m
    setForm(rest); setEditing(_idx); setModal(true)
  }
  const closeModal = () => setModal(false)

  const f = (key: keyof MarketingPayload) => ({
    value: form[key] as string,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm(p => ({ ...p, [key]: e.target.value })),
  })

  const handleSave = async () => {
    if (!form.title.trim()) { alert('El título es obligatorio'); return }
    setSaving(true)
    try {
      if (editing !== null) await updateMarketing(editing, form)
      else await createMarketing(form)
      await load()
      closeModal()
    } catch (err: any) {
      alert('Error al guardar: ' + err.message)
    } finally { setSaving(false) }
  }

  const handleDelete = async (id: number, title: string) => {
    if (!confirm(`¿Eliminar la promoción "${title}"? Esta acción no se puede deshacer.`)) return
    setDeleting(id)
    try {
      await deleteMarketing(id)
      await load()
    } catch (err: any) {
      alert('Error al eliminar: ' + err.message)
    } finally { setDeleting(null) }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Megaphone size={24} className="text-indigo-400" />
            Marketing
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            Ofertas y promociones de tiendas, del cine, o generales del mall — {promos.length} activas
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={load}
            className="p-2.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white rounded-xl transition-all"
            title="Recargar"
          >
            <RefreshCw size={18} />
          </button>
          <button
            onClick={openNew}
            className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-xl transition-all"
          >
            <Plus size={18} /> Nueva promoción
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-zinc-500 text-center py-12">Cargando...</div>
      ) : promos.length === 0 ? (
        <div className="text-zinc-500 text-center py-12 bg-zinc-900 rounded-2xl border border-zinc-800">
          Todavía no hay promociones cargadas.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {promos.map(promo => (
            <div key={promo._idx} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-white font-semibold text-sm leading-snug">{promo.title}</h3>
                <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${PRIORITY_COLORS[promo.priority]}`}>
                  {PRIORITY_LABELS[promo.priority]}
                </span>
              </div>
              <p className="text-zinc-500 text-xs">
                {promo.store_name ? `🏪 ${promo.store_name}` : '🏢 Promoción general del mall'}
              </p>
              {promo.description && <p className="text-zinc-400 text-xs line-clamp-2">{promo.description}</p>}
              {promo.valid_until && <p className="text-zinc-600 text-xs">Válido hasta: {promo.valid_until}</p>}
              {!promo.active && <p className="text-rose-400 text-xs font-medium">⏸️ Inactiva</p>}
              <div className="flex gap-2 mt-2 pt-2 border-t border-zinc-800">
                <button
                  onClick={() => openEdit(promo)}
                  className="flex items-center gap-1 text-xs text-zinc-400 hover:text-white transition-colors"
                >
                  <Pencil size={14} /> Editar
                </button>
                <button
                  onClick={() => handleDelete(promo._idx, promo.title)}
                  disabled={deleting === promo._idx}
                  className="flex items-center gap-1 text-xs text-rose-400 hover:text-rose-300 transition-colors disabled:opacity-50"
                >
                  <Trash2 size={14} /> {deleting === promo._idx ? 'Eliminando...' : 'Eliminar'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        open={modal}
        title={editing !== null ? 'Editar promoción' : 'Nueva promoción'}
        onClose={closeModal}
      >
        <div className="space-y-4">

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Título *</label>
            <input
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              placeholder="ej: 2x1 en pizzas medianas"
              {...f('title')}
            />
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">
              Tienda (opcional — déjalo vacío si es una promoción general del mall o del cine)
            </label>
            <select
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              value={form.store_id ?? ''}
              onChange={e => setForm(p => ({ ...p, store_id: e.target.value ? Number(e.target.value) : null }))}
            >
              <option value="">— Sin tienda asociada (general) —</option>
              {stores.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Descripción</label>
            <textarea
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 resize-none h-20"
              placeholder="Detalles de la promoción para que Any la explique bien..."
              {...f('description')}
            />
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Válido hasta (opcional)</label>
            <input
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              placeholder="ej: 31 de agosto, o Fin de semana"
              {...f('valid_until')}
            />
          </div>

          {editing !== null && (
            <div>
              <EntityPhotoGallery entityType="marketing" entityId={editing} accent="indigo" />
            </div>
          )}

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">
              Nivel de promoción — qué tanto Any la menciona proactivamente
            </label>
            <select
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              value={form.priority}
              onChange={e => setForm(p => ({ ...p, priority: Number(e.target.value) }))}
            >
              <option value={1}>1 - Baja (solo si preguntan)</option>
              <option value={2}>2 - Baja</option>
              <option value={3}>3 - Normal</option>
              <option value={4}>4 - Alta (la menciona seguido)</option>
              <option value={5}>5 - Máxima (la promociona activamente)</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="active"
              checked={form.active}
              onChange={e => setForm(p => ({ ...p, active: e.target.checked }))}
              className="w-4 h-4 rounded border-zinc-700 bg-zinc-800"
            />
            <label htmlFor="active" className="text-zinc-300 text-sm">Promoción activa</label>
          </div>

        </div>

        <div className="flex gap-3 justify-end mt-6 pt-5 border-t border-zinc-800">
          <button
            onClick={closeModal}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-all"
          >
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-sm text-white font-medium bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-xl transition-all"
          >
            {saving ? 'Guardando...' : editing !== null ? 'Guardar cambios' : 'Crear promoción'}
          </button>
        </div>
      </Modal>

    </div>
  )
}