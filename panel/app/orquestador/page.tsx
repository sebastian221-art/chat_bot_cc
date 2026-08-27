// 📄 ARCHIVO: panel/app/orquestador/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { getOrquestadorMapa, getOrquestadorTrazas, getOrquestadorFechas, limpiarOrquestadorTrazas, setOrquestadorSwitch } from '@/lib/api'
import { Cpu, Wrench, Activity, ChevronDown, ChevronRight, Clock, Zap, Bot, Power, RefreshCw, AlertTriangle, Download, Trash2, Calendar, Image as ImageIcon, MapPin } from 'lucide-react'

interface Herramienta { nombre: string; categoria: string; descripcion: string; palabras_clave: string[] }
interface Paso { paso: string; detalle: string; ms: number }
interface Traza {
  id: number; phone_number: string; mensaje_usuario: string
  herramienta_elegida: string; metodo_decision: string; razon_decision: string
  respuesta_bot: string; fotos_enviadas: number; ubicacion_enviada: string
  fotos_urls?: string[]; contenido_extra?: { tipo: string; detalle: string }[]
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
  const [telefonosPrueba, setTelefonosPrueba] = useState('573154559242')  // tu número por defecto
  const [trazas, setTrazas] = useState<Traza[]>([])
  const [openTraza, setOpenTraza] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [fechas, setFechas] = useState<string[]>([])
  const [fechaSel, setFechaSel] = useState<string>('')  // '' = todas las recientes

  const cargarMapa = async () => {
    const d = await getOrquestadorMapa()
    setHerramientas(d.herramientas)
    setSwitchModo(d.switch.modo)
    // Si ya hay números guardados, úsalos; si no, deja el tuyo por defecto
    if (d.switch.telefonos_prueba) setTelefonosPrueba(d.switch.telefonos_prueba)
  }
  const cargarTrazas = async (fecha?: string) => {
    const d = await getOrquestadorTrazas('prueba', fecha !== undefined ? fecha : fechaSel)
    setTrazas(d)
  }
  const cargarFechas = async () => {
    try {
      const f = await getOrquestadorFechas('prueba')
      setFechas(f)
    } catch { setFechas([]) }
  }

  const limpiarDia = async (fecha: string) => {
    if (!confirm(`¿Borrar todas las trazas del día ${fecha}? Esto no se puede deshacer.`)) return
    setSaving(true)
    try {
      const r = await limpiarOrquestadorTrazas({ fecha })
      alert(`Se borraron ${r.borradas} trazas del ${fecha}`)
      await cargarFechas()
      await cargarTrazas('')
      setFechaSel('')
    } catch (e: any) { alert('Error: ' + e.message) }
    finally { setSaving(false) }
  }

  const limpiarTodo = async () => {
    if (!confirm('¿Borrar TODAS las trazas de todos los días? Esto libera memoria pero no se puede deshacer.')) return
    setSaving(true)
    try {
      const r = await limpiarOrquestadorTrazas({ todo: true })
      alert(`Se borraron ${r.borradas} trazas en total`)
      await cargarFechas()
      await cargarTrazas('')
      setFechaSel('')
    } catch (e: any) { alert('Error: ' + e.message) }
    finally { setSaving(false) }
  }

  // Exporta las trazas a un archivo de texto legible — pensado para
  // revisar fácil y compartir. Incluye, por cada conversación: el
  // mensaje del cliente, qué herramienta eligió y cómo, el paso a paso,
  // y la respuesta exacta que dio el bot.
  const exportarTrazas = () => {
    if (trazas.length === 0) { alert('No hay trazas para exportar.'); return }
    const lineas: string[] = []
    lineas.push('═'.repeat(60))
    lineas.push('TRAZAS DEL ORQUESTADOR — Any (Centro Comercial El Puente)')
    lineas.push(`Exportado: ${new Date().toLocaleString('es-CO')}`)
    lineas.push(`Total de conversaciones: ${trazas.length}`)
    lineas.push('═'.repeat(60))
    lineas.push('')
    trazas.forEach((t, i) => {
      lineas.push(`${'─'.repeat(60)}`)
      lineas.push(`#${i + 1}  [${t.modo}]  ${t.created_at || ''}`)
      lineas.push('')
      lineas.push(`CLIENTE PREGUNTÓ: "${t.mensaje_usuario}"`)
      lineas.push('')
      lineas.push(`HERRAMIENTA ELEGIDA: ${t.herramienta_elegida}`)
      lineas.push(`MÉTODO DE DECISIÓN: ${t.metodo_decision}`)
      lineas.push(`POR QUÉ: ${t.razon_decision || '(no registrado)'}`)
      lineas.push('')
      lineas.push(`PASO A PASO (${t.pasos.length} pasos, ${t.tiempo_total_ms}ms total):`)
      t.pasos.forEach(p => lineas.push(`   [${p.ms}ms] ${p.paso}: ${p.detalle}`))
      lineas.push('')
      lineas.push(`ANY RESPONDIÓ:`)
      lineas.push(`"${t.respuesta_bot}"`)
      lineas.push(`   (${t.fotos_enviadas} fotos, ${t.ubicacion_enviada === 'si' ? 'con ubicación' : 'sin ubicación'})`)
      if (t.fotos_urls && t.fotos_urls.length > 0) {
        lineas.push(`   FOTOS ENVIADAS:`)
        t.fotos_urls.forEach(u => lineas.push(`      - ${u}`))
      }
      if (t.contenido_extra && t.contenido_extra.length > 0) {
        lineas.push(`   CONTENIDO AGREGADO:`)
        t.contenido_extra.forEach(c => lineas.push(`      - [${c.tipo}] ${c.detalle}`))
      }
      lineas.push('')
    })
    const blob = new Blob([lineas.join('\n')], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `trazas_orquestador_${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  useEffect(() => {
    Promise.all([cargarMapa(), cargarTrazas(), cargarFechas()]).finally(() => setLoading(false))
  }, [])

  const cambiarModo = async (modo: string) => {
    if (modo === 'produccion' && !confirm('¿Seguro? Esto hará que TODOS los clientes reales pasen por el orquestador nuevo.')) return
    setSaving(true)
    try {
      // Al activar "Solo pruebas", guardamos también el número autorizado
      // (el tuyo por defecto) para que quede listo de una vez.
      await setOrquestadorSwitch(modo, modo === 'solo_yo' ? telefonosPrueba : undefined)
      setSwitchModo(modo)
    } catch (e: any) {
      alert('Error: ' + e.message)
    } finally { setSaving(false) }
  }

  const guardarTelefonos = async () => {
    setSaving(true)
    try {
      await setOrquestadorSwitch(switchModo, telefonosPrueba)
      alert('Número de prueba guardado ✓')
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
        {switchModo === 'solo_yo' && (
          <div className="mt-4 pt-4 border-t border-zinc-800">
            <label className="text-zinc-300 text-xs font-medium block mb-2">
              Tu número de WhatsApp de prueba (el ÚNICO que pasa por el orquestador en este modo)
            </label>
            <p className="text-zinc-500 text-[11px] mb-2">
              Con código de país, sin espacios ni símbolos. Ej: 573154559242. Para varios, sepáralos con coma.
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={telefonosPrueba}
                onChange={e => setTelefonosPrueba(e.target.value)}
                placeholder="573154559242"
                className="flex-1 bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-600 focus:border-violet-500 focus:outline-none"
              />
              <button
                onClick={guardarTelefonos}
                disabled={saving}
                className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-all disabled:opacity-50"
              >
                Guardar
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-4">
        <button onClick={() => setTab('mapa')} className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${tab === 'mapa' ? 'bg-violet-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-white'}`}>
          <Wrench size={15} /> Mapa de herramientas
        </button>
        <button onClick={() => { setTab('trazas'); cargarTrazas(); cargarFechas() }} className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${tab === 'trazas' ? 'bg-violet-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-white'}`}>
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
          <div className="mb-3">
            <p className="text-zinc-500 text-xs mb-2">Conversaciones procesadas por el orquestador (solo pruebas). Haz clic para ver el paso a paso, las fotos enviadas y lo que se agregó.</p>
            {/* Barra de filtros y acciones */}
            <div className="flex items-center gap-2 flex-wrap bg-zinc-900 border border-zinc-800 rounded-xl p-2">
              <div className="flex items-center gap-1.5">
                <Calendar size={14} className="text-zinc-500" />
                <select
                  value={fechaSel}
                  onChange={e => { setFechaSel(e.target.value); cargarTrazas(e.target.value) }}
                  className="bg-zinc-950 border border-zinc-700 rounded-lg px-2 py-1.5 text-xs text-white focus:border-violet-500 focus:outline-none"
                >
                  <option value="">Todas las recientes</option>
                  {fechas.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
              <button onClick={exportarTrazas} className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium rounded-lg transition-all">
                <Download size={13} /> Exportar
              </button>
              <button onClick={() => cargarTrazas()} className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 text-xs rounded-lg">
                <RefreshCw size={13} /> Refrescar
              </button>
              <div className="flex-1" />
              {fechaSel && (
                <button onClick={() => limpiarDia(fechaSel)} disabled={saving}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 text-xs rounded-lg border border-amber-600/30">
                  <Trash2 size={13} /> Borrar día {fechaSel}
                </button>
              )}
              <button onClick={limpiarTodo} disabled={saving}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 text-xs rounded-lg border border-rose-600/30">
                <Trash2 size={13} /> Borrar todo
              </button>
            </div>
            <p className="text-zinc-600 text-[11px] mt-1.5">💡 Tip: borra los días viejos para ahorrar memoria. Si no eliges día, se borran los anteriores a hoy.</p>
          </div>
          {trazas.length === 0 ? (
            <div className="text-zinc-500 text-center py-12 bg-zinc-900 rounded-2xl border border-zinc-800">
              Sin trazas para mostrar. Activa el switch en "Solo pruebas" y manda mensajes de prueba para verlas aquí.
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
                          <span>📷 {t.fotos_enviadas} foto(s)</span>
                          <span>📍 {t.ubicacion_enviada === 'si' ? 'con ubicación' : 'sin ubicación'}</span>
                        </div>
                      </div>

                      {/* FOTOS ENVIADAS — con miniatura y link */}
                      {t.fotos_urls && t.fotos_urls.length > 0 && (
                        <div>
                          <p className="text-zinc-500 text-[11px] font-semibold mb-1.5 flex items-center gap-1">
                            <ImageIcon size={12} /> FOTOS ENVIADAS ({t.fotos_urls.length})
                          </p>
                          <div className="flex flex-wrap gap-2">
                            {t.fotos_urls.map((url, i) => (
                              <a key={i} href={url} target="_blank" rel="noopener noreferrer"
                                className="block bg-zinc-950 rounded-lg p-1.5 border border-zinc-800 hover:border-violet-500 transition-colors">
                                <img src={url} alt={`foto ${i + 1}`} className="w-24 h-24 object-cover rounded" />
                                <p className="text-[9px] text-zinc-600 mt-1 max-w-24 truncate">{url.split('/').pop()}</p>
                              </a>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* CONTENIDO AGREGADO — qué se añadió a la respuesta */}
                      {t.contenido_extra && t.contenido_extra.length > 0 && (
                        <div>
                          <p className="text-zinc-500 text-[11px] font-semibold mb-1.5">CONTENIDO AGREGADO A LA RESPUESTA</p>
                          <div className="space-y-1">
                            {t.contenido_extra.map((c, i) => (
                              <div key={i} className="flex items-start gap-2 bg-zinc-950 rounded-lg px-2.5 py-1.5 text-[11px]">
                                <span className="shrink-0">
                                  {c.tipo === 'foto' ? '📷' : c.tipo === 'ubicacion' ? '📍' : c.tipo === 'evento' ? '🎉' : c.tipo === 'sorteo' ? '🎁' : c.tipo === 'promocion' ? '🛍️' : '📎'}
                                </span>
                                <div className="min-w-0">
                                  <span className="text-violet-300 font-medium">{c.tipo}</span>
                                  <span className="text-zinc-500 ml-1.5 break-all">{c.detalle}</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
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