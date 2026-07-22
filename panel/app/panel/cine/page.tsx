// 📄 ARCHIVO: panel/app/panel/cine/page.tsx
'use client'
import { useState } from 'react'
import { Film, Plus, Trash2, Clock, Users, Star } from 'lucide-react'
import Modal from '@/components/Modal'

interface Movie {
  id: number; title: string; genre: string; duration: number
  rating: string; synopsis: string; active: boolean
}
interface Showtime {
  id: number; movieId: number; movieTitle: string
  date: string; time: string; room: string
  totalSeats: number; availableSeats: number; price: number
}

const ROOMS = ['Sala 1 (2D)','Sala 2 (3D)','Sala VIP','Sala 4DX']
const RATINGS = ['Todo público','+7','+12','+15','+18']

const DEMO_MOVIES: Movie[] = [
  { id:1, title:'Avengers: Secret Wars', genre:'Acción', duration:150, rating:'+12', synopsis:'Los Vengadores se enfrentan a su mayor amenaza.', active:true },
  { id:2, title:'Encanto 2', genre:'Animación', duration:105, rating:'Todo público', synopsis:'La familia Madrigal regresa con nuevas aventuras.', active:true },
]
const DEMO_SHOWS: Showtime[] = [
  { id:1, movieId:1, movieTitle:'Avengers: Secret Wars', date:'2026-03-15', time:'2:00 PM', room:'Sala 2 (3D)', totalSeats:120, availableSeats:45, price:16000 },
  { id:2, movieId:1, movieTitle:'Avengers: Secret Wars', date:'2026-03-15', time:'5:30 PM', room:'Sala 1 (2D)', totalSeats:150, availableSeats:110, price:13000 },
  { id:3, movieId:2, movieTitle:'Encanto 2', date:'2026-03-15', time:'3:00 PM', room:'Sala 1 (2D)', totalSeats:150, availableSeats:20, price:13000 },
]

export default function CinePage() {
  const [tab,       setTab]       = useState<'cartelera'|'funciones'|'config'>('cartelera')
  const [movies,    setMovies]    = useState<Movie[]>(DEMO_MOVIES)
  const [showtimes, setShowtimes] = useState<Showtime[]>(DEMO_SHOWS)
  const [showMovieModal, setShowMovieModal] = useState(false)
  const [showShowModal,  setShowShowModal]  = useState(false)
  const [newMovie,  setNewMovie]  = useState({ title:'', genre:'', duration:90, rating:'Todo público', synopsis:'' })
  const [newShow,   setNewShow]   = useState({ movieId:0, date:'', time:'', room:'Sala 1 (2D)', totalSeats:150, price:13000 })

  const occupancyColor = (available: number, total: number) => {
    const pct = available / total
    if (pct < 0.2) return 'text-red-400'
    if (pct < 0.5) return 'text-amber-400'
    return 'text-emerald-400'
  }

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2"><Film size={22} className="text-blue-400"/> Cine Colombia</h1>
          <p className="text-zinc-500 text-sm mt-0.5">Panel Cine · Piso 3</p>
        </div>
      </div>

      {/* Stats rápidas */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label:'Películas activas', value: movies.filter(m=>m.active).length, color:'text-blue-400' },
          { label:'Funciones hoy',     value: showtimes.length,                   color:'text-indigo-400' },
          { label:'Sillas disponibles',value: showtimes.reduce((a,s)=>a+s.availableSeats,0), color:'text-emerald-400' },
        ].map(s => (
          <div key={s.label} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
            <p className="text-zinc-500 text-xs uppercase tracking-wider">{s.label}</p>
            <p className={`text-2xl font-bold mt-1 ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded-xl p-1 w-fit">
        {(['cartelera','funciones','config'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-xs font-medium transition-all ${tab===t?'bg-blue-600 text-white':'text-zinc-400 hover:text-white'}`}>
            {t==='cartelera'?'🎬 Cartelera':t==='funciones'?'🕐 Funciones':'⚙️ Salas'}
          </button>
        ))}
      </div>

      {tab==='cartelera' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button onClick={() => setShowMovieModal(true)} className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium px-4 py-2.5 rounded-xl">
              <Plus size={14}/> Agregar película
            </button>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {movies.map(m => (
              <div key={m.id} className={`bg-zinc-900 border rounded-2xl p-5 ${m.active?'border-zinc-800':'border-zinc-800 opacity-50'}`}>
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <p className="text-white font-bold">{m.title}</p>
                    <p className="text-zinc-500 text-xs mt-0.5">{m.genre} · {m.duration} min</p>
                  </div>
                  <span className="text-xs text-blue-400 bg-blue-400/10 border border-blue-400/20 px-2 py-1 rounded-lg">{m.rating}</span>
                </div>
                <p className="text-zinc-400 text-xs leading-relaxed mb-3">{m.synopsis}</p>
                <div className="flex gap-2">
                  <button onClick={() => setMovies(prev => prev.map(p => p.id===m.id?{...p,active:!p.active}:p))}
                    className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-all ${m.active?'bg-zinc-800 text-zinc-400 hover:bg-zinc-700':'bg-blue-600 text-white hover:bg-blue-500'}`}>
                    {m.active?'Ocultar':'Mostrar en cartelera'}
                  </button>
                  <button onClick={() => setMovies(prev => prev.filter(p => p.id!==m.id))}
                    className="p-1.5 text-zinc-600 hover:text-red-400 bg-zinc-800 rounded-lg">
                    <Trash2 size={13}/>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab==='funciones' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button onClick={() => setShowShowModal(true)} className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium px-4 py-2.5 rounded-xl">
              <Plus size={14}/> Nueva función
            </button>
          </div>
          <div className="space-y-3">
            {showtimes.map(s => (
              <div key={s.id} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <p className="text-white font-semibold text-sm truncate">{s.movieTitle}</p>
                  <p className="text-zinc-500 text-xs mt-0.5 flex items-center gap-3">
                    <span className="flex items-center gap-1"><Clock size={10}/> {s.date} · {s.time}</span>
                    <span>{s.room}</span>
                  </p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className={`text-sm font-bold flex items-center gap-1 justify-end ${occupancyColor(s.availableSeats, s.totalSeats)}`}>
                    <Users size={12}/> {s.availableSeats}/{s.totalSeats}
                  </p>
                  <p className="text-zinc-500 text-xs">${s.price.toLocaleString('es-CO')}</p>
                </div>
                <button onClick={() => setShowtimes(prev => prev.filter(x => x.id!==s.id))}
                  className="p-1.5 text-zinc-600 hover:text-red-400 bg-zinc-800 rounded-lg flex-shrink-0">
                  <Trash2 size={13}/>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab==='config' && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {ROOMS.map(room => (
            <div key={room} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center justify-between">
              <div>
                <p className="text-white font-semibold text-sm">{room}</p>
                <p className="text-zinc-500 text-xs mt-0.5">
                  {showtimes.filter(s => s.room===room).length} función(es) programadas hoy
                </p>
              </div>
              <span className="text-xs text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-2 py-1 rounded-lg">Operativa</span>
            </div>
          ))}
        </div>
      )}

      {/* Modal película */}
      <Modal open={showMovieModal} onClose={() => setShowMovieModal(false)} title="Agregar película">
        <div className="space-y-3">
          {[{k:'title',l:'Título *'},{k:'genre',l:'Género'},{k:'synopsis',l:'Sinopsis'}].map(({k,l}) => (
            <div key={k}><label className="text-zinc-400 text-xs block mb-1">{l}</label>
              <input value={(newMovie as any)[k]} onChange={e => setNewMovie(p => ({...p,[k]:e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"/>
            </div>
          ))}
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-zinc-400 text-xs block mb-1">Duración (min)</label>
              <input type="number" value={newMovie.duration} onChange={e => setNewMovie(p => ({...p,duration:+e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"/>
            </div>
            <div><label className="text-zinc-400 text-xs block mb-1">Clasificación</label>
              <select value={newMovie.rating} onChange={e => setNewMovie(p => ({...p,rating:e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                {RATINGS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          </div>
          <button disabled={!newMovie.title} onClick={() => { setMovies(p => [...p,{id:Date.now(),...newMovie,active:true}]); setShowMovieModal(false); setNewMovie({title:'',genre:'',duration:90,rating:'Todo público',synopsis:''}) }}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl text-sm">
            Agregar película
          </button>
        </div>
      </Modal>

      {/* Modal función */}
      <Modal open={showShowModal} onClose={() => setShowShowModal(false)} title="Nueva función">
        <div className="space-y-3">
          <div><label className="text-zinc-400 text-xs block mb-1">Película</label>
            <select value={newShow.movieId} onChange={e => setNewShow(p => ({...p,movieId:+e.target.value}))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
              <option value={0}>Seleccionar...</option>
              {movies.filter(m=>m.active).map(m => <option key={m.id} value={m.id}>{m.title}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-zinc-400 text-xs block mb-1">Fecha</label>
              <input type="date" value={newShow.date} onChange={e => setNewShow(p => ({...p,date:e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"/>
            </div>
            <div><label className="text-zinc-400 text-xs block mb-1">Hora</label>
              <input type="time" value={newShow.time} onChange={e => setNewShow(p => ({...p,time:e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"/>
            </div>
          </div>
          <div><label className="text-zinc-400 text-xs block mb-1">Sala</label>
            <select value={newShow.room} onChange={e => setNewShow(p => ({...p,room:e.target.value}))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
              {ROOMS.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-zinc-400 text-xs block mb-1">Sillas</label>
              <input type="number" value={newShow.totalSeats} onChange={e => setNewShow(p => ({...p,totalSeats:+e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"/>
            </div>
            <div><label className="text-zinc-400 text-xs block mb-1">Precio (COP)</label>
              <input type="number" value={newShow.price} onChange={e => setNewShow(p => ({...p,price:+e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"/>
            </div>
          </div>
          <button disabled={!newShow.movieId||!newShow.date} onClick={() => {
            const movie = movies.find(m=>m.id===newShow.movieId)
            setShowtimes(p => [...p, { id:Date.now(), ...newShow, availableSeats:newShow.totalSeats, movieTitle:movie?.title||'' }])
            setShowShowModal(false)
            setNewShow({movieId:0,date:'',time:'',room:'Sala 1 (2D)',totalSeats:150,price:13000})
          }} className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl text-sm">
            Crear función
          </button>
        </div>
      </Modal>
    </div>
  )
}