// 📄 ARCHIVO: panel/app/panel/entretenimiento/page.tsx
'use client'
import { useState } from 'react'
import { Gamepad2, Plus, Trash2, Users, Clock, Tag, ToggleRight, ToggleLeft } from 'lucide-react'
import Modal from '@/components/Modal'

interface Activity {
  id: number; name: string; category: string; description: string
  price: number; duration: number; minAge: number; maxCapacity: number
  currentOccupancy: number; active: boolean
}
interface Schedule { day: string; open: string; close: string; active: boolean }

const CATEGORIES = ['Juegos de arcade','Realidad virtual','Trampolines','Laberinto','Zona infantil','Billar','Ping pong','Otros']

const DEMO_ACTIVITIES: Activity[] = [
  { id:1, name:'Zona de Arcade', category:'Juegos de arcade', description:'Más de 50 máquinas arcade clásicas y modernas', price:15000, duration:60, minAge:5, maxCapacity:80, currentOccupancy:25, active:true },
  { id:2, name:'Realidad Virtual', category:'Realidad virtual', description:'Experiencias VR de última generación', price:25000, duration:30, minAge:10, maxCapacity:20, currentOccupancy:8, active:true },
  { id:3, name:'Trampolines', category:'Trampolines', description:'Zona de saltos y acrobacias supervisadas', price:18000, duration:60, minAge:6, maxCapacity:40, currentOccupancy:12, active:true },
  { id:4, name:'Laberinto 3D', category:'Laberinto', description:'Laberinto de espejos y efectos visuales', price:10000, duration:30, minAge:4, maxCapacity:30, currentOccupancy:0, active:false },
]

const DEMO_SCHEDULE: Schedule[] = [
  { day:'Lunes – Viernes', open:'11:00', close:'21:00', active:true },
  { day:'Sábados',         open:'10:00', close:'22:00', active:true },
  { day:'Domingos',        open:'10:00', close:'21:00', active:true },
  { day:'Festivos',        open:'10:00', close:'22:00', active:true },
]

export default function EntretenimientoPage() {
  const [tab,        setTab]        = useState<'actividades'|'horarios'|'aforo'>('actividades')
  const [activities, setActivities] = useState<Activity[]>(DEMO_ACTIVITIES)
  const [schedule,   setSchedule]   = useState<Schedule[]>(DEMO_SCHEDULE)
  const [showModal,  setShowModal]  = useState(false)
  const [newAct,     setNewAct]     = useState({ name:'', category:'Juegos de arcade', description:'', price:0, duration:60, minAge:5, maxCapacity:30 })

  const totalOccupancy = activities.reduce((a,x)=>a+(x.active?x.currentOccupancy:0),0)
  const totalCapacity  = activities.reduce((a,x)=>a+(x.active?x.maxCapacity:0),0)
  const pctFull = totalCapacity > 0 ? Math.round(totalOccupancy/totalCapacity*100) : 0

  const occupancyColor = (curr: number, max: number) => {
    const p = curr/max
    if (p >= 0.9) return 'text-red-400 bg-red-400/10'
    if (p >= 0.6) return 'text-amber-400 bg-amber-400/10'
    return 'text-emerald-400 bg-emerald-400/10'
  }

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2"><Gamepad2 size={22} className="text-pink-400"/> Happy City</h1>
          <p className="text-zinc-500 text-sm mt-0.5">Panel Entretenimiento · Piso 3</p>
        </div>
        <div className={`px-3 py-1.5 rounded-full border text-xs font-semibold ${pctFull>80?'bg-red-500/10 text-red-400 border-red-500/20':pctFull>50?'bg-amber-500/10 text-amber-400 border-amber-500/20':'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'}`}>
          {pctFull}% de aforo
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label:'Actividades activas', value:`${activities.filter(a=>a.active).length}`, color:'text-pink-400' },
          { label:'Personas ahora',      value:`${totalOccupancy}`,                         color:'text-indigo-400' },
          { label:'Capacidad total',     value:`${totalCapacity}`,                           color:'text-zinc-300' },
        ].map(s => (
          <div key={s.label} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
            <p className="text-zinc-500 text-xs uppercase tracking-wider">{s.label}</p>
            <p className={`text-2xl font-bold mt-1 ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded-xl p-1 w-fit">
        {(['actividades','horarios','aforo'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-xs font-medium transition-all ${tab===t?'bg-pink-600 text-white':'text-zinc-400 hover:text-white'}`}>
            {t==='actividades'?'🎮 Actividades':t==='horarios'?'🕐 Horarios':'👥 Aforo en vivo'}
          </button>
        ))}
      </div>

      {tab==='actividades' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button onClick={() => setShowModal(true)} className="flex items-center gap-2 bg-pink-600 hover:bg-pink-500 text-white text-xs font-medium px-4 py-2.5 rounded-xl">
              <Plus size={14}/> Agregar actividad
            </button>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {activities.map(a => (
              <div key={a.id} className={`bg-zinc-900 border rounded-2xl p-5 ${a.active?'border-zinc-800':'border-zinc-800 opacity-50'}`}>
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <p className="text-white font-bold">{a.name}</p>
                    <p className="text-zinc-500 text-xs flex items-center gap-2 mt-0.5">
                      <span className="flex items-center gap-1"><Tag size={10}/>{a.category}</span>
                      <span className="flex items-center gap-1"><Clock size={10}/>{a.duration} min</span>
                      <span>+{a.minAge} años</span>
                    </p>
                  </div>
                  <p className="text-pink-400 font-bold text-sm">${a.price.toLocaleString('es-CO')}</p>
                </div>
                <p className="text-zinc-400 text-xs mb-3">{a.description}</p>
                <div className="flex items-center justify-between mb-3">
                  <span className={`text-xs px-2 py-1 rounded-lg font-medium ${occupancyColor(a.currentOccupancy, a.maxCapacity)}`}>
                    <Users size={10} className="inline mr-1"/>{a.currentOccupancy}/{a.maxCapacity} personas
                  </span>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setActivities(prev => prev.map(x => x.id===a.id?{...x,active:!x.active}:x))}
                    className="flex-1 flex items-center justify-center gap-1.5 text-xs text-zinc-400 hover:text-white bg-zinc-800 py-1.5 rounded-lg">
                    {a.active?<ToggleRight size={13} className="text-emerald-400"/>:<ToggleLeft size={13}/>}
                    {a.active?'Activa':'Inactiva'}
                  </button>
                  <button onClick={() => setActivities(prev => prev.filter(x=>x.id!==a.id))} className="p-1.5 text-zinc-600 hover:text-red-400 bg-zinc-800 rounded-lg"><Trash2 size={13}/></button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab==='horarios' && (
        <div className="max-w-lg space-y-3">
          {schedule.map((s, i) => (
            <div key={s.day} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center gap-4">
              <button onClick={() => setSchedule(prev => prev.map((x,j)=>j===i?{...x,active:!x.active}:x))}
                className={`relative w-9 h-5 rounded-full transition-colors flex-shrink-0 ${s.active?'bg-pink-500':'bg-zinc-700'}`}>
                <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${s.active?'translate-x-4':'translate-x-0.5'}`}/>
              </button>
              <p className="text-white text-sm font-medium flex-1">{s.day}</p>
              <div className="flex items-center gap-2">
                <input type="time" value={s.open} onChange={e => setSchedule(prev=>prev.map((x,j)=>j===i?{...x,open:e.target.value}:x))}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-white text-xs focus:outline-none w-24"/>
                <span className="text-zinc-600 text-xs">–</span>
                <input type="time" value={s.close} onChange={e => setSchedule(prev=>prev.map((x,j)=>j===i?{...x,close:e.target.value}:x))}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-white text-xs focus:outline-none w-24"/>
              </div>
            </div>
          ))}
          <button className="w-full py-2.5 bg-pink-600 hover:bg-pink-500 text-white text-sm font-medium rounded-xl transition-all">
            Guardar horarios
          </button>
        </div>
      )}

      {tab==='aforo' && (
        <div className="space-y-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
            <p className="text-white font-semibold mb-3">Aforo en tiempo real</p>
            <div className="w-full bg-zinc-800 rounded-full h-3 mb-2">
              <div className={`h-3 rounded-full transition-all ${pctFull>80?'bg-red-500':pctFull>50?'bg-amber-500':'bg-emerald-500'}`} style={{width:`${pctFull}%`}}/>
            </div>
            <p className="text-zinc-400 text-xs">{totalOccupancy} personas de {totalCapacity} máximo ({pctFull}% ocupado)</p>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {activities.filter(a=>a.active).map(a => (
              <div key={a.id} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
                <div className="flex justify-between items-center mb-2">
                  <p className="text-white text-sm font-medium">{a.name}</p>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${occupancyColor(a.currentOccupancy,a.maxCapacity)}`}>
                    {a.currentOccupancy}/{a.maxCapacity}
                  </span>
                </div>
                <div className="w-full bg-zinc-800 rounded-full h-1.5">
                  <div className={`h-1.5 rounded-full transition-all ${a.currentOccupancy/a.maxCapacity>0.8?'bg-red-500':a.currentOccupancy/a.maxCapacity>0.5?'bg-amber-500':'bg-emerald-500'}`}
                    style={{width:`${Math.min(100,a.currentOccupancy/a.maxCapacity*100)}%`}}/>
                </div>
                <div className="flex gap-2 mt-3">
                  <button onClick={() => setActivities(p=>p.map(x=>x.id===a.id?{...x,currentOccupancy:Math.max(0,x.currentOccupancy-1)}:x))}
                    className="flex-1 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white text-xs rounded-lg">− Salida</button>
                  <button onClick={() => setActivities(p=>p.map(x=>x.id===a.id&&x.currentOccupancy<x.maxCapacity?{...x,currentOccupancy:x.currentOccupancy+1}:x))}
                    className="flex-1 py-1 bg-zinc-800 hover:bg-pink-600 text-zinc-400 hover:text-white text-xs rounded-lg">+ Entrada</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <Modal open={showModal} onClose={() => setShowModal(false)} title="Agregar actividad">
        <div className="space-y-3">
          <div><label className="text-zinc-400 text-xs block mb-1">Nombre *</label>
            <input value={newAct.name} onChange={e=>setNewAct(p=>({...p,name:e.target.value}))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-pink-500"/>
          </div>
          <div><label className="text-zinc-400 text-xs block mb-1">Categoría</label>
            <select value={newAct.category} onChange={e=>setNewAct(p=>({...p,category:e.target.value}))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-pink-500">
              {CATEGORIES.map(c=><option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div><label className="text-zinc-400 text-xs block mb-1">Descripción</label>
            <input value={newAct.description} onChange={e=>setNewAct(p=>({...p,description:e.target.value}))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-pink-500"/>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {[{k:'price',l:'Precio (COP)'},{k:'duration',l:'Duración (min)'},{k:'minAge',l:'Edad mínima'},{k:'maxCapacity',l:'Cap. máxima'}].map(({k,l})=>(
              <div key={k}><label className="text-zinc-400 text-xs block mb-1">{l}</label>
                <input type="number" value={(newAct as any)[k]} onChange={e=>setNewAct(p=>({...p,[k]:+e.target.value}))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-pink-500"/>
              </div>
            ))}
          </div>
          <button disabled={!newAct.name} onClick={() => { setActivities(p=>[...p,{id:Date.now(),...newAct,currentOccupancy:0,active:true}]); setShowModal(false); setNewAct({name:'',category:'Juegos de arcade',description:'',price:0,duration:60,minAge:5,maxCapacity:30}) }}
            className="w-full bg-pink-600 hover:bg-pink-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl text-sm">
            Agregar actividad
          </button>
        </div>
      </Modal>
    </div>
  )
}