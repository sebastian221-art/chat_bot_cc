// 📄 ARCHIVO: panel/app/orquestador/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { getOrquestadorMapa, getOrquestadorTrazas, setOrquestadorSwitch } from '@/lib/api'
import { Cpu, Wrench, Activity, ChevronDown, ChevronRight, Clock, Zap, Bot, Power, RefreshCw, AlertTriangle } from 'lucide-react'

interface Herramienta { nombre: string; categoria: string; descripcion: string; palabras_clave: string[] }
interface Paso { paso: string; detalle: string; ms: number }
interface Traza {
  id: number; phone_number: string; mensaje_usuario: string
  herramienta_elegida: string; metodo_decision: string; razon_decision: string
  respuesta_bot: string; fotos_enviadas: number; ubicacion_enviada: string
  pasos: Paso[]; tiempo_total_ms: number; modo: string; created_at: string
}

const CAT_COLOR: Record<string, string> = {
  'Seguridad': 'text-rose-400 bg-rose-500/10',
  'Atención': 'text-amber-400 bg-amber-500/10',
  'Acción': 'text-sky-400 bg-sky-500/10',
  'Información': 'text-emerald-400 bg-emerald-500/10',
  'Conversación': 'text-violet-400 bg-violet-500/10',
}
const MODOS = [
  { id: 'off', label: 'Apagado', desc: 'Todo por el flujo viejo', color: 'zinc' },
  { id: 'solo_yo', label: 'Solo pruebas', desc: 'Solo mis mensajes de prueba', color: 'amber' },
  { id: 'produccion', label: 'Producción', desc: 'Todos los clientes', color: 'emerald' },
]

export default function OrquestadorPage() {
  const [tab, setTab] = useState<'mapa' | 'trazas'>('mapa')
  const [herramientas, setHerramientas] = useState<Herramienta[]>([])
  const [switchModo, setSwitchModo] = useState('off')
  const [trazas, setTrazas] = useState<Traza[]>([])
  const [openTraza, setOpenTraza] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const cargarMapa = async () => {
    const d = await getOrquestadorMapa()
    setHerramientas(d.herramientas)
    setSwitchModo(d.switch.modo)
  }
  const cargarTrazas = async () => {
    const d = await getOrquestadorTrazas('prueba')
    setTrazas(d)
  }

  useEffect(() => {
    Promise.all([cargarMapa(), cargarTrazas()]).finally(() => setLoading(false))
  }, [])

  const cambiarModo = async (modo: string) => {
    if (modo === 'produccion' && !confirm('¿Seguro? Esto hará que TODOS los clientes reales pasen por el orquestador nuevo.')) return
    setSaving(true)
    try {
      await setOrquestadorSwitch(modo)
      setSwitchModo(modo)
    } catch (e: any) {
      alert('Error: ' + e.message)
    } finally { setSaving(false) }
  }

  if (loading) return <div className="p-8 text-zinc-500">Cargando el orquestador...</div>

  return (
    <div className="p-6 max-w-4xl mx-auto pb-20">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Cpu size={24} className="text-violet-400" /> Orquestador Central
        </h1>
        <p className="text-zinc-500 text-sm mt-1">El cerebro del flujo nuevo — sus herramientas, sus decisiones, y el interruptor. En construcción.</p>
      </div>

      {/* Switch */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Power size={16} className="text-violet-400" />
          <span className="text-white text-sm font-semibold">Interruptor de flujo</span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {MODOS.map(m => (
            <button key={m.id} onClick={() => cambiarModo(m.id)} disabled={saving}
              className={`text-left p-3 rounded-xl border transition-all ${
                switchModo === m.id
                  ? 'border-violet-500 bg-violet-500/10'
                  : 'border-zinc-800 bg-zinc-950 hover:border-zinc-700'
              }`}>
              <p className={`text-sm font-semibold ${switchModo === m.id ? 'text-violet-300' : 'text-zinc-300'}`}>{m.label}</p>
              <p className="text-zinc-500 text-[11px] mt-0.5">{m.desc}</p>
            </button>
          ))}
        </div>
        {switchModo === 'produccion' && (
          <div className="flex items-center gap-2 mt-3 text-amber-400 text-xs">
            <AlertTriangle size={14} /> El orquestador está atendiendo a clientes reales.
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-4">
        <button onClick={() => setTab('mapa')} className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${tab === 'mapa' ? 'bg-violet-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-white'}`}>
          <Wrench size={15} /> Mapa de herramientas
        </button>
        <button onClick={() => { setTab('trazas'); cargarTrazas() }} className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${tab === 'trazas' ? 'bg-violet-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-white'}`}>
          <Activity size={15} /> Trazas en vivo
        </button>
      </div>

      {/* Vista A — Mapa de herramientas */}
      {tab === 'mapa' && (
        <div className="space-y-3">
          <p className="text-zinc-500 text-xs mb-2">Todo lo que el orquestador sabe hacer. Cuando llega un mensaje, elige una de estas herramientas (por reglas o con IA).</p>
          {herramientas.map((h, i) => (
            <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-white text-sm font-semibold">{h.nombre}</span>
                <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${CAT_COLOR[h.categoria] || 'text-zinc-400 bg-zinc-800'}`}>{h.categoria}</span>
              </div>
              <p className="text-zinc-400 text-xs leading-relaxed">{h.descripcion}</p>
              {h.palabras_clave.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {h.palabras_clave.slice(0, 8).map((k, j) => (
                    <span key={j} className="text-[10px] bg-zinc-800 text-zinc-500 px-1.5 py-0.5 rounded">{k}</span>
                  ))}
                  {h.palabras_clave.length > 8 && <span className="text-[10px] text-zinc-600">+{h.palabras_clave.length - 8}</span>}
                </div>
              )}
              {h.palabras_clave.length === 0 && (
                <p className="text-zinc-600 text-[11px] mt-2 italic">Se decide con IA o lógica especial (sin palabras clave fijas)</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Vista B — Trazas en vivo */}
      {tab === 'trazas' && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-zinc-500 text-xs">Últimas conversaciones procesadas por el orquestador (solo pruebas). Haz clic para ver el paso a paso.</p>
            <button onClick={cargarTrazas} className="p-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded-lg"><RefreshCw size={14} /></button>
          </div>
          {trazas.length === 0 ? (
            <div className="text-zinc-500 text-center py-12 bg-zinc-900 rounded-2xl border border-zinc-800">
              Sin trazas todavía. Activa el switch en "Solo pruebas" y manda mensajes de prueba para verlas aquí.
            </div>
          ) : (
            <div className="space-y-2">
              {trazas.map(t => (
                <div key={t.id} className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
                  <button onClick={() => setOpenTraza(openTraza === t.id ? null : t.id)} className="w-full flex items-start justify-between p-4 hover:bg-zinc-850 transition-colors text-left">
                    <div className="min-w-0 flex-1">
                      <p className="text-white text-sm font-medium truncate">"{t.mensaje_usuario}"</p>
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        <span className="text-[11px] bg-violet-500/10 text-violet-300 px-2 py-0.5 rounded-full font-medium">{t.herramienta_elegida}</span>
                        <span className="text-[11px] text-zinc-500 flex items-center gap-1">
                          {t.metodo_decision === 'ia' ? <Bot size={11} /> : <Zap size={11} />}
                          {t.metodo_decision}
                        </span>
                        <span className="text-[11px] text-zinc-600 flex items-center gap-1"><Clock size={11} /> {t.tiempo_total_ms}ms</span>
                      </div>
                    </div>
                    <div className="shrink-0 ml-2 mt-0.5">{openTraza === t.id ? <ChevronDown size={16} className="text-zinc-500" /> : <ChevronRight size={16} className="text-zinc-500" />}</div>
                  </button>
                  {openTraza === t.id && (
                    <div className="px-4 pb-4 border-t border-zinc-800 pt-3 space-y-3">
                      <div>
                        <p className="text-zinc-500 text-[11px] font-semibold mb-1">POR QUÉ ELIGIÓ ESTA HERRAMIENTA</p>
                        <p className="text-zinc-300 text-xs">{t.razon_decision}</p>
                      </div>
                      <div>
                        <p className="text-zinc-500 text-[11px] font-semibold mb-1.5">PASO A PASO ({t.pasos.length} pasos)</p>
                        <div className="space-y-1.5">
                          {t.pasos.map((p, i) => (
                            <div key={i} className="flex items-start gap-2 bg-zinc-950 rounded-lg px-3 py-2">
                              <span className="text-[10px] text-zinc-600 font-mono shrink-0 mt-0.5">{p.ms}ms</span>
                              <div className="min-w-0">
                                <span className="text-violet-300 text-[11px] font-medium">{p.paso}</span>
                                <p className="text-zinc-400 text-[11px] leading-relaxed">{p.detalle}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="text-zinc-500 text-[11px] font-semibold mb-1">RESPUESTA AL CLIENTE</p>
                        <p className="text-zinc-300 text-xs bg-zinc-950 rounded-lg p-3 whitespace-pre-wrap">{t.respuesta_bot}</p>
                        <div className="flex gap-3 mt-1.5 text-[11px] text-zinc-600">
                          <span>📷 {t.fotos_enviadas} fotos</span>
                          <span>📍 {t.ubicacion_enviada === 'si' ? 'con ubicación' : 'sin ubicación'}</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}