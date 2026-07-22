// 📄 ARCHIVO: panel/app/panel/parqueadero/page.tsx
'use client'
import { useState } from 'react'
import { Car, Bike, Truck, RefreshCw, TrendingUp, Clock, DollarSign, Plus, Trash2 } from 'lucide-react'
import Modal from '@/components/Modal'

interface Zone { id: number; name: string; type: 'carro'|'moto'|'discapacitados'; total: number; occupied: number; active: boolean }
interface Rate { id: number; label: string; minutes: number; price: number }
interface Vehicle { plate: string; zone: string; entryTime: string; paid: boolean }

const DEMO_ZONES: Zone[] = [
  { id:1, name:'Zona A — Nivel 1', type:'carro',          total:80,  occupied:52, active:true },
  { id:2, name:'Zona B — Nivel 2', type:'carro',          total:80,  occupied:31, active:true },
  { id:3, name:'Zona C — Sótano',  type:'carro',          total:60,  occupied:60, active:true },
  { id:4, name:'Motos',            type:'moto',           total:40,  occupied:18, active:true },
  { id:5, name:'Discapacitados',   type:'discapacitados', total:8,   occupied:2,  active:true },
]
const DEMO_RATES: Rate[] = [
  { id:1, label:'Primera hora',   minutes:60,  price:2000 },
  { id:2, label:'Hora adicional', minutes:60,  price:1500 },
  { id:3, label:'Fracción (30 min)', minutes:30, price:1000 },
  { id:4, label:'Moto — 1ra hora', minutes:60, price:1000 },
  { id:5, label:'Día completo (carros)', minutes:720, price:12000 },
]
const DEMO_VEHICLES: Vehicle[] = [
  { plate:'ABC123', zone:'Zona A — Nivel 1', entryTime:'10:32', paid:false },
  { plate:'XYZ789', zone:'Zona B — Nivel 2', entryTime:'09:15', paid:true  },
  { plate:'DEF456', zone:'Zona C — Sótano',  entryTime:'11:05', paid:false },
]

function minsAgo(timeStr: string) {
  const [h, m] = timeStr.split(':').map(Number)
  const now = new Date()
  const entry = new Date(); entry.setHours(h, m, 0)
  return Math.max(0, Math.floor((now.getTime() - entry.getTime()) / 60000))
}

function calcPrice(rates: Rate[], mins: number) {
  const r1 = rates.find(r => r.label === 'Primera hora')
  const rA = rates.find(r => r.label === 'Hora adicional')
  if (!r1 || !rA) return 0
  if (mins <= 60) return r1.price
  const extra = Math.ceil((mins - 60) / 60)
  return r1.price + extra * rA.price
}

export default function ParqueaderoPage() {
  const [tab,      setTab]      = useState<'estado'|'tarifas'|'vehiculos'|'reporte'>('estado')
  const [zones,    setZones]    = useState<Zone[]>(DEMO_ZONES)
  const [rates,    setRates]    = useState<Rate[]>(DEMO_RATES)
  const [vehicles, setVehicles] = useState<Vehicle[]>(DEMO_VEHICLES)
  const [showRateModal,    setShowRateModal]    = useState(false)
  const [showVehicleModal, setShowVehicleModal] = useState(false)
  const [newRate,    setNewRate]    = useState({ label:'', minutes:60, price:0 })
  const [newVehicle, setNewVehicle] = useState({ plate:'', zone:DEMO_ZONES[0].name })
  const [refreshing, setRefreshing] = useState(false)

  const totalSpots     = zones.filter(z => z.active && z.type === 'carro').reduce((a,z) => a + z.total, 0)
  const occupiedSpots  = zones.filter(z => z.active && z.type === 'carro').reduce((a,z) => a + z.occupied, 0)
  const availableSpots = totalSpots - occupiedSpots
  const pct = totalSpots > 0 ? Math.round(occupiedSpots / totalSpots * 100) : 0

  const pctColor = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500'
  const pctText  = pct >= 90 ? 'text-red-400' : pct >= 70 ? 'text-amber-400' : 'text-emerald-400'
  const pctBadge = pct >= 90 ? 'text-red-400 bg-red-500/10 border-red-500/20' : pct >= 70 ? 'text-amber-400 bg-amber-500/10 border-amber-500/20' : 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'

  const zoneIcon = (type: Zone['type']) =>
    type === 'moto' ? <Bike size={14}/> : type === 'discapacitados' ? <span className="text-xs">♿</span> : <Car size={14}/>

  return (
    <div className="p-6 space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Car size={22} className="text-amber-400"/> Parqueadero
          </h1>
          <p className="text-zinc-500 text-sm mt-0.5">CC El Puente · Nivel 1, 2 y Sótano</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-3 py-1.5 rounded-full border text-xs font-semibold ${pctBadge}`}>
            {pct}% ocupado
          </span>
          <button onClick={() => { setRefreshing(true); setTimeout(() => setRefreshing(false), 600) }}
            disabled={refreshing}
            className="p-2 text-zinc-400 hover:text-white bg-zinc-800 rounded-lg disabled:opacity-50 transition-all">
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''}/>
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {[
          { icon: Car,      label:'Disponibles',    value: availableSpots, sub:'carros', color:'text-emerald-400', bg:'bg-emerald-500/10' },
          { icon: Car,      label:'Ocupados',        value: occupiedSpots,  sub:'carros', color:'text-amber-400',   bg:'bg-amber-500/10'   },
          { icon: Bike,     label:'Motos disponibles', value: zones.find(z=>z.type==='moto') ? zones.find(z=>z.type==='moto')!.total - zones.find(z=>z.type==='moto')!.occupied : 0, sub:'espacios', color:'text-blue-400', bg:'bg-blue-500/10' },
          { icon: TrendingUp, label:'Ingresos hoy',  value:'$84.000', sub:'estimado', color:'text-indigo-400', bg:'bg-indigo-500/10' },
        ].map(s => {
          const Icon = s.icon
          return (
            <div key={s.label} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
              <div className={`w-8 h-8 rounded-xl ${s.bg} flex items-center justify-center mb-2`}>
                <Icon size={15} className={s.color}/>
              </div>
              <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
              <p className="text-zinc-500 text-xs mt-0.5">{s.label}</p>
            </div>
          )
        })}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded-xl p-1 w-fit">
        {(['estado','tarifas','vehiculos','reporte'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-xs font-medium transition-all ${tab===t ? 'bg-amber-500 text-zinc-900' : 'text-zinc-400 hover:text-white'}`}>
            {t==='estado' ? '🅿️ Zonas' : t==='tarifas' ? '💰 Tarifas' : t==='vehiculos' ? '🚗 Vehículos' : '📊 Reporte'}
          </button>
        ))}
      </div>

      {/* Tab: Estado de zonas */}
      {tab === 'estado' && (
        <div className="space-y-3">
          {/* Barra global */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
            <div className="flex justify-between mb-2">
              <p className="text-white font-semibold text-sm">Ocupación general — Carros</p>
              <p className={`text-sm font-bold ${pctText}`}>{pct}%</p>
            </div>
            <div className="w-full bg-zinc-800 rounded-full h-3">
              <div className={`h-3 rounded-full transition-all ${pctColor}`} style={{ width: `${pct}%` }}/>
            </div>
            <p className="text-zinc-500 text-xs mt-2">{occupiedSpots} de {totalSpots} espacios ocupados · {availableSpots} disponibles</p>
          </div>

          {/* Zonas individuales */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {zones.map(z => {
              const avail = z.total - z.occupied
              const zPct  = Math.round(z.occupied / z.total * 100)
              const zColor = zPct >= 100 ? 'bg-red-500' : zPct >= 75 ? 'bg-amber-500' : 'bg-emerald-500'
              const zText  = zPct >= 100 ? 'text-red-400' : zPct >= 75 ? 'text-amber-400' : 'text-emerald-400'
              return (
                <div key={z.id} className={`bg-zinc-900 border rounded-2xl p-4 transition-all ${z.active ? 'border-zinc-800' : 'border-zinc-800 opacity-50'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-white text-sm font-semibold flex items-center gap-2">
                      <span className="text-zinc-400">{zoneIcon(z.type)}</span>
                      {z.name}
                    </p>
                    <p className={`text-sm font-bold ${zText}`}>{avail} libres</p>
                  </div>
                  <div className="w-full bg-zinc-800 rounded-full h-1.5 mb-2">
                    <div className={`h-1.5 rounded-full transition-all ${zColor}`} style={{ width: `${Math.min(100, zPct)}%` }}/>
                  </div>
                  <div className="flex items-center justify-between">
                    <p className="text-zinc-500 text-xs">{z.occupied}/{z.total} espacios</p>
                    <div className="flex gap-2">
                      <button onClick={() => setZones(p => p.map(x => x.id===z.id && x.occupied > 0 ? {...x, occupied: x.occupied-1} : x))}
                        className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white text-xs rounded-lg transition-all">− Salida</button>
                      <button onClick={() => setZones(p => p.map(x => x.id===z.id && x.occupied < x.total ? {...x, occupied: x.occupied+1} : x))}
                        className="px-2 py-1 bg-zinc-800 hover:bg-amber-500/20 text-zinc-400 hover:text-amber-400 text-xs rounded-lg transition-all">+ Entrada</button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Estado que ve el bot */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
            <p className="text-zinc-400 text-xs font-semibold uppercase tracking-wider mb-2">Vista previa — Respuesta del bot</p>
            <div className="bg-zinc-950 rounded-xl p-3">
              <p className="text-zinc-300 text-sm font-mono leading-relaxed whitespace-pre-wrap">{
`🅿️ *Parqueadero CC El Puente*

${zones.filter(z=>z.type==='carro' && z.active).map(z => {
  const a = z.total - z.occupied
  const emoji = a === 0 ? '🔴' : a < 10 ? '🟡' : '🟢'
  return `${emoji} ${z.name}: *${a} espacios*`
}).join('\n')}

🏍️ Motos: *${(zones.find(z=>z.type==='moto')?.total||0) - (zones.find(z=>z.type==='moto')?.occupied||0)} espacios*`}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Tarifas */}
      {tab === 'tarifas' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button onClick={() => setShowRateModal(true)} className="flex items-center gap-2 bg-amber-500 hover:bg-amber-400 text-zinc-900 text-xs font-semibold px-4 py-2.5 rounded-xl">
              <Plus size={14}/> Nueva tarifa
            </button>
          </div>
          <div className="space-y-2">
            {rates.map(r => (
              <div key={r.id} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 bg-amber-500/10 rounded-xl flex items-center justify-center">
                    <DollarSign size={14} className="text-amber-400"/>
                  </div>
                  <div>
                    <p className="text-white text-sm font-medium">{r.label}</p>
                    <p className="text-zinc-500 text-xs flex items-center gap-1">
                      <Clock size={10}/> {r.minutes} min
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <p className="text-amber-400 font-bold">${r.price.toLocaleString('es-CO')}</p>
                  <button onClick={() => setRates(p => p.filter(x => x.id !== r.id))}
                    className="p-1.5 text-zinc-600 hover:text-red-400 bg-zinc-800 hover:bg-red-500/10 rounded-lg transition-all">
                    <Trash2 size={13}/>
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Vista previa bot */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
            <p className="text-zinc-400 text-xs font-semibold uppercase tracking-wider mb-2">Vista previa — Respuesta del bot</p>
            <div className="bg-zinc-950 rounded-xl p-3">
              <p className="text-zinc-300 text-sm font-mono leading-relaxed whitespace-pre-wrap">{
`💰 *Tarifas de parqueadero*

${rates.map(r => `• ${r.label}: *$${r.price.toLocaleString('es-CO')}*`).join('\n')}

💳 Pago: efectivo o Nequi en la taquilla`}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Vehículos */}
      {tab === 'vehiculos' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button onClick={() => setShowVehicleModal(true)} className="flex items-center gap-2 bg-amber-500 hover:bg-amber-400 text-zinc-900 text-xs font-semibold px-4 py-2.5 rounded-xl">
              <Plus size={14}/> Registrar entrada
            </button>
          </div>
          <div className="space-y-3">
            {vehicles.map((v, i) => {
              const mins = minsAgo(v.entryTime)
              const precio = calcPrice(rates, mins)
              return (
                <div key={i} className={`bg-zinc-900 border rounded-2xl p-4 flex items-center justify-between gap-4 ${!v.paid ? 'border-zinc-800' : 'border-emerald-500/20 opacity-60'}`}>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-zinc-800 rounded-xl flex items-center justify-center">
                      <Car size={16} className="text-zinc-400"/>
                    </div>
                    <div>
                      <p className="text-white font-bold tracking-wider">{v.plate}</p>
                      <p className="text-zinc-500 text-xs">{v.zone}</p>
                    </div>
                  </div>
                  <div className="text-center">
                    <p className="text-zinc-300 text-sm font-medium">Entrada {v.entryTime}</p>
                    <p className="text-zinc-500 text-xs">{mins} min adentro</p>
                  </div>
                  <div className="text-right flex items-center gap-2">
                    <div>
                      <p className="text-amber-400 font-bold">${precio.toLocaleString('es-CO')}</p>
                      <p className="text-zinc-500 text-xs">{v.paid ? '✅ Pagado' : 'Pendiente'}</p>
                    </div>
                    {!v.paid && (
                      <button onClick={() => setVehicles(p => p.map((x,j) => j===i ? {...x, paid:true} : x))}
                        className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg transition-all">
                        Cobrar
                      </button>
                    )}
                    <button onClick={() => setVehicles(p => p.filter((_,j) => j!==i))}
                      className="p-1.5 text-zinc-600 hover:text-red-400 bg-zinc-800 rounded-lg">
                      <Trash2 size={13}/>
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Tab: Reporte */}
      {tab === 'reporte' && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {[
            { label:'Vehículos hoy',      value:'127',      sub:'entradas registradas',  color:'text-amber-400'   },
            { label:'Ingresos del día',    value:'$84.000',  sub:'estimado en tarifas',   color:'text-emerald-400' },
            { label:'Tiempo promedio',     value:'1h 20min', sub:'estadía por vehículo',  color:'text-blue-400'    },
            { label:'Hora pico',           value:'12:00 – 2pm', sub:'mayor ocupación',   color:'text-indigo-400'  },
            { label:'Zona más ocupada',    value:'Zona C — Sótano', sub:'100% ocupado',  color:'text-red-400'     },
            { label:'Motos registradas',   value:'34',       sub:'entradas del día',      color:'text-zinc-300'    },
          ].map(s => (
            <div key={s.label} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
              <p className="text-zinc-500 text-xs uppercase tracking-wider mb-1">{s.label}</p>
              <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
              <p className="text-zinc-600 text-xs mt-0.5">{s.sub}</p>
            </div>
          ))}
          <div className="xl:col-span-2 bg-amber-500/5 border border-amber-500/15 rounded-2xl p-4">
            <p className="text-amber-400 text-xs font-semibold uppercase tracking-wider mb-1">💡 Integración futura</p>
            <p className="text-zinc-400 text-sm">
              Conecta sensores de ocupación en tiempo real para que el bot informe disponibilidad exacta por zona al instante. Contacta al equipo técnico para la integración.
            </p>
          </div>
        </div>
      )}

      {/* Modal tarifa */}
      <Modal open={showRateModal} onClose={() => setShowRateModal(false)} title="Nueva tarifa">
        <div className="space-y-3">
          <div><label className="text-zinc-400 text-xs block mb-1">Descripción *</label>
            <input value={newRate.label} onChange={e => setNewRate(p => ({...p, label: e.target.value}))}
              placeholder="Ej: Día completo motos"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500"/>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-zinc-400 text-xs block mb-1">Duración (min)</label>
              <input type="number" value={newRate.minutes} onChange={e => setNewRate(p => ({...p, minutes: +e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500"/>
            </div>
            <div><label className="text-zinc-400 text-xs block mb-1">Precio (COP)</label>
              <input type="number" value={newRate.price} onChange={e => setNewRate(p => ({...p, price: +e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500"/>
            </div>
          </div>
          <button disabled={!newRate.label || !newRate.price}
            onClick={() => { setRates(p => [...p, { id: Date.now(), ...newRate }]); setShowRateModal(false); setNewRate({ label:'', minutes:60, price:0 }) }}
            className="w-full bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-zinc-900 font-semibold py-2.5 rounded-xl text-sm">
            Agregar tarifa
          </button>
        </div>
      </Modal>

      {/* Modal vehículo */}
      <Modal open={showVehicleModal} onClose={() => setShowVehicleModal(false)} title="Registrar entrada">
        <div className="space-y-3">
          <div><label className="text-zinc-400 text-xs block mb-1">Placa *</label>
            <input value={newVehicle.plate} onChange={e => setNewVehicle(p => ({...p, plate: e.target.value.toUpperCase()}))}
              placeholder="ABC123"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm font-mono focus:outline-none focus:border-amber-500 uppercase"/>
          </div>
          <div><label className="text-zinc-400 text-xs block mb-1">Zona</label>
            <select value={newVehicle.zone} onChange={e => setNewVehicle(p => ({...p, zone: e.target.value}))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500">
              {zones.map(z => <option key={z.id} value={z.name}>{z.name}</option>)}
            </select>
          </div>
          <button disabled={!newVehicle.plate}
            onClick={() => {
              const now = new Date()
              setVehicles(p => [...p, { ...newVehicle, entryTime: `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`, paid: false }])
              setZones(p => p.map(z => z.name === newVehicle.zone ? {...z, occupied: Math.min(z.total, z.occupied+1)} : z))
              setShowVehicleModal(false)
              setNewVehicle({ plate:'', zone: DEMO_ZONES[0].name })
            }}
            className="w-full bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-zinc-900 font-semibold py-2.5 rounded-xl text-sm">
            Registrar entrada
          </button>
        </div>
      </Modal>
    </div>
  )
}