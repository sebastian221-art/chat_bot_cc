// 📄 ARCHIVO: panel/app/info-general/page.tsx
'use client'
import { useEffect, useState } from 'react'
import {
  getMallInfo, updateMallInfo, MallInfo,
  getInfoPoints, createInfoPoint, updateInfoPoint, deleteInfoPoint, InfoPoint,
} from '@/lib/api'
import Modal from '@/components/Modal'
import { Building2, Plus, Pencil, Trash2, RefreshCw, MapPinned, Save } from 'lucide-react'

const EMPTY_MALL: MallInfo = { name: '', address: '', general_schedule: '', phone: '', parking: '', wifi: '' }
const EMPTY_POINT: InfoPoint = { name: '', floor: '', location: '' }

export default function InfoGeneralPage() {
  const [mallInfo, setMallInfo] = useState<MallInfo>(EMPTY_MALL)
  const [points, setPoints]     = useState<(InfoPoint & { _idx: number })[]>([])
  const [loading, setLoading]   = useState(true)
  const [savingMall, setSavingMall] = useState(false)
  const [modal, setModal]       = useState(false)
  const [editing, setEditing]   = useState<number | null>(null)
  const [form, setForm]         = useState<InfoPoint>(EMPTY_POINT)
  const [saving, setSaving]     = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const [mall, pts] = await Promise.all([getMallInfo(), getInfoPoints()])
      setMallInfo(mall)
      setPoints(pts.map((p: InfoPoint) => ({ ...p, _idx: p.id! })))
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const mallField = (key: keyof MallInfo) => ({
    value: (mallInfo[key] as string) || '',
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setMallInfo(p => ({ ...p, [key]: e.target.value })),
  })

  const handleSaveMallInfo = async () => {
    setSavingMall(true)
    try {
      await updateMallInfo(mallInfo)
      alert('✅ Información general actualizada')
    } catch (err: any) {
      alert('Error al guardar: ' + err.message)
    } finally {
      setSavingMall(false)
    }
  }

  const openNewPoint = () => { setForm(EMPTY_POINT); setEditing(null); setModal(true) }
  const openEditPoint = (p: InfoPoint & { _idx: number }) => {
    setForm({ name: p.name, floor: p.floor, location: p.location })
    setEditing(p._idx)
    setModal(true)
  }
  const closeModal = () => setModal(false)

  const handleSavePoint = async () => {
    if (!form.name.trim()) {
      alert('El nombre es obligatorio')
      return
    }
    setSaving(true)
    try {
      if (editing !== null) {
        await updateInfoPoint(editing, form)
      } else {
        await createInfoPoint(form)
      }
      setModal(false)
      await load()
    } catch (err: any) {
      alert('Error al guardar: ' + err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDeletePoint = async (id: number) => {
    if (!confirm('¿Eliminar este punto de interés?')) return
    setDeleting(id)
    try {
      await deleteInfoPoint(id)
      await load()
    } catch (err: any) {
      alert('Error al eliminar: ' + err.message)
    } finally {
      setDeleting(null)
    }
  }

  const pointField = (key: keyof InfoPoint) => ({
    value: (form[key] as string) || '',
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm(p => ({ ...p, [key]: e.target.value })),
  })

  if (loading) {
    return <div className="p-8 text-center text-zinc-600 animate-pulse">Cargando información general...</div>
  }

  return (
    <div className="p-8">

      {/* Header */}
      <div className="flex items-center justify-between mb-7">
        <div>
          <h1 className="text-2xl font-bold text-white">Información General del Mall</h1>
          <p className="text-zinc-500 text-sm mt-0.5">
            Dirección, teléfono, horario general y puntos de interés — lo que Any usa como base de todo
          </p>
        </div>
        <button
          onClick={load}
          className="p-2 text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-all"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Formulario de info general */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 mb-8">
        <div className="flex items-center gap-2 mb-5">
          <Building2 size={16} className="text-indigo-400" />
          <h2 className="text-white font-semibold text-sm">Datos generales</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Nombre del mall *</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" {...mallField('name')} />
          </div>
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Teléfono de contacto</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" placeholder="ej: 3174320138" {...mallField('phone')} />
          </div>
          <div className="md:col-span-2">
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Dirección</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" placeholder="ej: Calle 10 # 12-184, San Gil, Santander" {...mallField('address')} />
          </div>
          <div className="md:col-span-2">
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Horario general</label>
            <textarea className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 resize-none h-20" {...mallField('general_schedule')} />
          </div>
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Parqueadero</label>
            <textarea className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 resize-none h-16" {...mallField('parking')} />
          </div>
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">WiFi</label>
            <textarea className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 resize-none h-16" placeholder="ej: Red 'CC_ElPuente_Free', sin contraseña" {...mallField('wifi')} />
          </div>
        </div>

        <div className="flex justify-end mt-5">
          <button
            onClick={handleSaveMallInfo}
            disabled={savingMall}
            className="flex items-center gap-2 px-5 py-2.5 text-sm text-white font-medium bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-xl transition-all"
          >
            <Save size={14} /> {savingMall ? 'Guardando...' : 'Guardar cambios'}
          </button>
        </div>
      </div>

      {/* Puntos de interés */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <MapPinned size={16} className="text-emerald-400" />
          <h2 className="text-white font-semibold text-sm">Puntos de interés</h2>
          <span className="text-zinc-500 text-xs">({points.length})</span>
        </div>
        <button
          onClick={openNewPoint}
          className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium px-4 py-2 rounded-xl transition-all"
        >
          <Plus size={14} /> Nuevo punto
        </button>
      </div>

      {points.length === 0 ? (
        <div className="text-center text-zinc-600 py-10 bg-zinc-900 border border-zinc-800 rounded-2xl">
          Sin puntos de interés todavía — agrega baños, cajeros, accesos, etc.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {points.map(p => (
            <div key={p._idx} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-white font-medium text-sm truncate">{p.name}</p>
                <p className="text-zinc-500 text-xs mt-0.5">{p.floor} {p.location ? `· ${p.location}` : ''}</p>
              </div>
              <div className="flex gap-1.5 flex-shrink-0">
                <button onClick={() => openEditPoint(p)} className="p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded-lg transition-all">
                  <Pencil size={13} />
                </button>
                <button
                  onClick={() => handleDeletePoint(p._idx)}
                  disabled={deleting === p._idx}
                  className="p-1.5 text-zinc-500 hover:text-rose-400 hover:bg-zinc-800 rounded-lg transition-all disabled:opacity-40"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal punto de interés */}
      <Modal open={modal} title={editing !== null ? 'Editar punto' : 'Nuevo punto de interés'} onClose={closeModal} size="md">
        <div className="space-y-4">
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Nombre *</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-emerald-500" placeholder="ej: Punto de pago" {...pointField('name')} />
          </div>
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Piso</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-emerald-500" placeholder="ej: Piso 1" {...pointField('floor')} />
          </div>
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Ubicación exacta</label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-emerald-500" placeholder="ej: Frente a la entrada principal" {...pointField('location')} />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-zinc-800">
          <button onClick={closeModal} className="px-4 py-2 text-sm text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-all">
            Cancelar
          </button>
          <button onClick={handleSavePoint} disabled={saving} className="px-4 py-2 text-sm text-white font-medium bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-xl transition-all">
            {saving ? 'Guardando...' : 'Guardar'}
          </button>
        </div>
      </Modal>
    </div>
  )
}