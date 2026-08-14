// 📄 ARCHIVO: panel/app/sorteos/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { getRaffles, createRaffle, updateRaffle, toggleRaffle, deleteRaffle, Raffle } from '@/lib/api'
import Modal from '@/components/Modal'
import ImageUpload from '@/components/ImageUpload'
import { Gift, Plus, Pencil, Trash2, RefreshCw, Power, Calendar, MapPin } from 'lucide-react'

const EMPTY: Raffle = { name: '', prize: '', requirements: '', end_date: '', location: '', description: '', priority: 3, photo_url: '' }

const PRIORITY_LABELS: Record<number, string> = { 1: 'Baja', 2: 'Baja', 3: 'Normal', 4: 'Alta', 5: 'Máxima' }
const PRIORITY_COLORS: Record<number, string> = {
  1: 'bg-zinc-800 text-zinc-500', 2: 'bg-zinc-800 text-zinc-500',
  3: 'bg-indigo-500/10 text-indigo-400', 4: 'bg-amber-500/10 text-amber-400',
  5: 'bg-rose-500/10 text-rose-400',
}

export default function SorteosPage() {
  const [raffles, setRaffles]   = useState<(Raffle & { _idx: number })[]>([])
  const [loading, setLoading]   = useState(true)
  const [modal, setModal]       = useState(false)
  const [editing, setEditing]   = useState<number | null>(null)
  const [form, setForm]         = useState<Raffle>(EMPTY)
  const [saving, setSaving]     = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await getRaffles()
      setRaffles(data.map((r: Raffle) => ({ ...r, _idx: r.id! })))
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const openNew = () => { setForm(EMPTY); setEditing(null); setModal(true) }
  const openEdit = (r: Raffle & { _idx: number }) => {
    const { _idx, active, ...rest } = r
    setForm(rest); setEditing(_idx); setModal(true)
  }
  const closeModal = () => setModal(false)

  const handleSave = async () => {
    if (!form.name.trim() || !form.prize.trim()) {
      alert('Nombre y premio son obligatorios')
      return
    }
    setSaving(true)
    try {
      if (editing !== null) await updateRaffle(editing, form)
      else await createRaffle(form)
      setModal(false)
      await load()
    } catch (err: any) {
      alert('Error al guardar: ' + err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async (id: number) => {
    try { await toggleRaffle(id); await load() }
    catch (err: any) { alert('Error: ' + err.message) }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('¿Eliminar este sorteo?')) return
    setDeleting(id)
    try { await deleteRaffle(id); await load() }
    catch (err: any) { alert('Error al eliminar: ' + err.message) }
    finally { setDeleting(null) }
  }

  const field = (key: keyof Raffle) => ({
    value: (form[key] as string) || '',
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm(p => ({ ...p, [key]: e.target.value })),
  })

  return (
    <div className="p-8">

      {/* Header */}
      <div className="flex items-center justify-between mb-7">
        <div>
          <h1 className="text-2xl font-bold text-white">Sorteos y Campañas</h1>
          <p className="text-zinc-500 text-sm mt-0.5">{raffles.length} sorteos — distinto de Eventos: tienen premio y requisitos de participación</p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="p-2 text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-all">
            <RefreshCw size={14} />
          </button>
          <button
            onClick={openNew}
            className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium px-4 py-2 rounded-xl transition-all"
          >
            <Plus size={14} /> Nuevo sorteo
          </button>
        </div>
      </div>

      {/* Lista */}
      {loading ? (
        <div className="text-center text-zinc-600 py-16 animate-pulse">Cargando sorteos...</div>
      ) : raffles.length === 0 ? (
        <div className="text-center text-zinc-600 py-16">
          <Gift size={32} className="mx-auto mb-3 text-zinc-700" />
          Todavía no hay sorteos — agrega el primero
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {raffles.map(r => (
            <div key={r._idx} className={`bg-zinc-900 border rounded-2xl p-5 ${r.active ? 'border-zinc-800' : 'border-zinc-800/50 opacity-60'}`}>
              <div className="flex items-start justify-between mb-2.5">
                <div className="flex items-center gap-2">
                  <Gift size={16} className="text-amber-400 flex-shrink-0" />
                  <h3 className="text-white font-semibold text-sm">{r.name}</h3>
                  {!r.active && (
                    <span className="text-[10px] text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded-full">Inactivo</span>
                  )}
                </div>
                <div className="flex gap-1.5 flex-shrink-0">
                  <button
                    onClick={() => handleToggle(r._idx)}
                    title={r.active ? 'Desactivar' : 'Activar'}
                    className={`p-1.5 rounded-lg transition-all ${r.active ? 'text-emerald-400 hover:bg-zinc-800' : 'text-zinc-600 hover:bg-zinc-800'}`}
                  >
                    <Power size={13} />
                  </button>
                  <button onClick={() => openEdit(r)} className="p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded-lg transition-all">
                    <Pencil size={13} />
                  </button>
                  <button
                    onClick={() => handleDelete(r._idx)}
                    disabled={deleting === r._idx}
                    className="p-1.5 text-zinc-500 hover:text-rose-400 hover:bg-zinc-800 rounded-lg transition-all disabled:opacity-40"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>

              <p className="text-amber-300 text-sm font-medium mb-2">🎁 {r.prize}</p>

              {r.description && <p className="text-zinc-400 text-xs leading-relaxed mb-3">{r.description}</p>}
              {r.requirements && (
                <p className="text-zinc-500 text-xs leading-relaxed mb-3">
                  <span className="font-semibold text-zinc-400">Cómo participar:</span> {r.requirements}
                </p>
              )}

              <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-zinc-800">
                {r.end_date && (
                  <span className="text-zinc-500 text-xs flex items-center gap-1"><Calendar size={11} /> {r.end_date}</span>
                )}
                {r.location && (
                  <span className="text-zinc-500 text-xs flex items-center gap-1"><MapPin size={11} /> {r.location}</span>
                )}
                <span className={`ml-auto px-2 py-0.5 rounded-lg text-xs font-semibold ${PRIORITY_COLORS[r.priority] || PRIORITY_COLORS[3]}`}>
                  📢 {PRIORITY_LABELS[r.priority] || 'Normal'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      <Modal open={modal} title={editing !== null ? 'Editar sorteo' : 'Nuevo sorteo'} onClose={closeModal} size="md">
        <div className="space-y-4">
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Nombre *</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500" placeholder="ej: Sorteo de un carro" {...field('name')} />
          </div>
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Premio *</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500" placeholder="ej: Un Renault Kwid 0km" {...field('prize')} />
          </div>
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Cómo participar</label>
            <textarea className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500 resize-none h-20" placeholder="ej: Regístrate en la Administración del CC, Piso 2" {...field('requirements')} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Fecha límite</label>
              <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500" placeholder="ej: 30 de agosto" {...field('end_date')} />
            </div>
            <div>
              <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Dónde registrarse</label>
              <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500" placeholder="ej: Piso 2, admin" {...field('location')} />
            </div>
          </div>
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Descripción</label>
            <textarea className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500 resize-none h-16" {...field('description')} />
          </div>
          <div>
            <ImageUpload
              value={form.photo_url || ''}
              onChange={url => setForm(p => ({ ...p, photo_url: url }))}
              label="Foto / afiche del sorteo"
              accent="amber"
            />
          </div>
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">
              Nivel de promoción — qué tanto Any lo menciona proactivamente
            </label>
            <select
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500"
              value={form.priority}
              onChange={e => setForm(p => ({ ...p, priority: Number(e.target.value) }))}
            >
              <option value={1}>1 - Baja (solo si preguntan)</option>
              <option value={2}>2 - Baja</option>
              <option value={3}>3 - Normal</option>
              <option value={4}>4 - Alta (lo menciona seguido)</option>
              <option value={5}>5 - Máxima (lo promociona activamente)</option>
            </select>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-zinc-800">
          <button onClick={closeModal} className="px-4 py-2 text-sm text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-all">
            Cancelar
          </button>
          <button onClick={handleSave} disabled={saving} className="px-4 py-2 text-sm text-white font-medium bg-amber-600 hover:bg-amber-500 disabled:opacity-50 rounded-xl transition-all">
            {saving ? 'Guardando...' : 'Guardar'}
          </button>
        </div>
      </Modal>
    </div>
  )
}