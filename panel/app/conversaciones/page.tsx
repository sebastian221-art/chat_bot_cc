// 📄 ARCHIVO: panel/app/conversaciones/page.tsx
'use client'
import { useEffect, useState, useCallback } from 'react'
import { getConversations, getConversationHistory, sendManualReply, resumeBot, ConvUser } from '@/lib/api'
import { RefreshCw, User, Clock, MessageSquare, Sparkles, AlertTriangle, Send, PauseCircle } from 'lucide-react'

interface Message {
  role:      string
  message:   string
  timestamp: string
}

interface UserProfile {
  summary?:    string
  interests?:  string
  fav_stores?: string
  visit_freq?: string
}

interface ConvUserExt extends ConvUser {
  profile?: UserProfile
}

export default function ConversacionesPage() {
  const [users, setUsers]           = useState<ConvUserExt[]>([])
  const [selected, setSelected]     = useState<string | null>(null)
  const [history, setHistory]       = useState<Message[]>([])
  const [loadingH, setLoadingH]     = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdate, setLastUpdate] = useState(new Date())
  const [replyText, setReplyText]   = useState('')
  const [sending, setSending]       = useState(false)

  const loadUsers = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true)
    try {
      const data = await getConversations()
      // El backend devuelve array directo en /conversations
      setUsers(Array.isArray(data) ? data : [])
      setLastUpdate(new Date())
    } catch (e) {
      console.error(e)
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { loadUsers() }, [loadUsers])

  useEffect(() => {
    const interval = setInterval(() => loadUsers(true), 30_000)
    return () => clearInterval(interval)
  }, [loadUsers])

  const selectUser = async (phone: string) => {
    setSelected(phone)
    setLoadingH(true)
    setHistory([])
    try {
      const data = await getConversationHistory(phone)
      // El backend devuelve { phone, messages: [...] }
      const msgs = Array.isArray(data) ? data : (data?.messages ?? [])
      setHistory(msgs)
    } catch (e) {
      console.error(e)
      setHistory([])
    } finally {
      setLoadingH(false)
    }
  }

  const selectedUser = users.find(u => u.phone === selected)

  const handleSendReply = async () => {
    if (!selected || !replyText.trim()) return
    setSending(true)
    try {
      await sendManualReply(selected, replyText.trim())
      setReplyText('')
      await selectUser(selected)
      await loadUsers(true)
    } catch (e: any) {
      alert('Error al enviar: ' + e.message)
    } finally {
      setSending(false)
    }
  }

  const freqColor = (freq?: string): string => {
    const map: Record<string, string> = {
      frecuente: 'text-emerald-400 bg-emerald-400/10',
      regular:   'text-indigo-400 bg-indigo-400/10',
      ocasional: 'text-zinc-400 bg-zinc-700',
    }
    return map[freq ?? 'ocasional'] ?? 'text-zinc-400 bg-zinc-700'
  }

  return (
    <div className="flex" style={{ height: '100vh', overflow: 'hidden' }}>

      {/* ── Lista de usuarios ── */}
      <div className="flex flex-col bg-zinc-950 border-r border-zinc-800" style={{ width: '300px', flexShrink: 0 }}>
        <div className="p-4 border-b border-zinc-800 flex items-center justify-between">
          <div>
            <h2 className="text-white font-semibold">Conversaciones</h2>
            <p className="text-zinc-500 text-xs mt-0.5">{users.length} usuarios</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-600">
              {lastUpdate.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}
            </span>
            <button
              onClick={() => loadUsers(true)}
              disabled={refreshing}
              className="p-1.5 text-zinc-500 hover:text-white rounded-lg hover:bg-zinc-800 transition-all disabled:opacity-40"
            >
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-zinc-800/60">
          {users.length === 0 ? (
            <div className="p-8 text-center text-zinc-600 text-sm">
              Sin conversaciones aún
            </div>
          ) : users.map(u => (
            <button
              key={u.phone}
              onClick={() => selectUser(u.phone)}
              className={`w-full text-left px-4 py-3.5 hover:bg-zinc-900 transition-colors ${
                selected === u.phone ? 'bg-zinc-900 border-l-2 border-indigo-500' : ''
              } ${u.needs_human ? 'bg-rose-950/20' : ''}`}
            >
              <div className="flex items-start gap-3">
                <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
                  u.needs_human ? 'bg-rose-600/20' : 'bg-indigo-600/20'
                }`}>
                  {u.needs_human
                    ? <AlertTriangle size={15} className="text-rose-400" />
                    : <User size={15} className="text-indigo-400" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="text-white text-sm font-medium truncate">{u.name || 'Sin nombre'}</p>
                    {u.needs_human && (
                      <span className="text-rose-400 text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-rose-500/15 flex-shrink-0">
                        NECESITA ATENCIÓN
                      </span>
                    )}
                    {u.bot_paused && !u.needs_human && (
                      <span className="text-amber-400 text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-amber-500/15 flex-shrink-0 flex items-center gap-0.5">
                        <PauseCircle size={9} /> PAUSADO
                      </span>
                    )}
                  </div>
                  <p className="text-zinc-500 text-xs truncate">{u.phone}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-zinc-600 text-xs flex items-center gap-1">
                      <MessageSquare size={10} /> {u.total}
                    </span>
                    {u.profile?.visit_freq && (
                      <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${freqColor(u.profile.visit_freq)}`}>
                        {u.profile.visit_freq}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* ── Panel derecho ── */}
      <div className="flex-1 flex flex-col bg-zinc-950 overflow-hidden">
        {selected ? (
          <>
            <div className="border-b border-zinc-800 p-4 flex-shrink-0">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-white font-semibold">{selectedUser?.name || 'Sin nombre'}</h3>
                  <p className="text-zinc-500 text-xs">{selected}</p>
                </div>
                <span className="text-zinc-600 text-xs flex items-center gap-1">
                  <Clock size={11} />
                  {lastUpdate.toLocaleDateString('es-CO')}
                </span>
              </div>

              {selectedUser?.needs_human && (
                <div className="mt-3 p-3 bg-rose-950/40 border border-rose-900/50 rounded-xl flex items-center justify-between gap-3">
                  <div className="flex items-start gap-2">
                    <AlertTriangle size={14} className="text-rose-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-rose-400 text-xs font-semibold">Esta conversación necesita atención humana</p>
                      {selectedUser.escalation_reason && (
                        <p className="text-zinc-500 text-xs mt-0.5">Detectado por: "{selectedUser.escalation_reason}"</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {selectedUser?.bot_paused && (
                <div className="mt-3 p-3 bg-amber-950/30 border border-amber-900/40 rounded-xl flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <PauseCircle size={14} className="text-amber-400 flex-shrink-0" />
                    <p className="text-amber-400 text-xs font-medium">El bot está en pausa — solo tú estás respondiendo</p>
                  </div>
                  <button
                    onClick={async () => { if (selected) { await resumeBot(selected); await loadUsers() } }}
                    className="text-xs text-amber-300 hover:text-white bg-amber-500/10 hover:bg-amber-500/20 px-2.5 py-1 rounded-lg transition-all flex-shrink-0"
                  >
                    Devolver al bot
                  </button>
                </div>
              )}

              {selectedUser?.profile?.summary && (
                <div className="mt-3 p-3 bg-indigo-950/40 border border-indigo-900/50 rounded-xl">
                  <p className="text-indigo-400 text-xs font-medium flex items-center gap-1.5 mb-1.5">
                    <Sparkles size={11} /> Perfil IA
                  </p>
                  <p className="text-zinc-300 text-xs leading-relaxed">{selectedUser.profile.summary}</p>
                  {selectedUser.profile.interests && (
                    <p className="text-zinc-500 text-xs mt-1.5">🎯 {selectedUser.profile.interests}</p>
                  )}
                  {selectedUser.profile.fav_stores && (
                    <p className="text-zinc-500 text-xs mt-0.5">🏪 {selectedUser.profile.fav_stores}</p>
                  )}
                </div>
              )}
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-3">
              {loadingH ? (
                <div className="text-center text-zinc-600 py-12 animate-pulse">Cargando historial...</div>
              ) : history.length === 0 ? (
                <div className="text-center text-zinc-600 py-12">Sin mensajes aún</div>
              ) : (
                history.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[72%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-indigo-600 text-white rounded-br-sm'
                        : msg.role === 'admin'
                        ? 'bg-emerald-700 text-white rounded-bl-sm'
                        : 'bg-zinc-800 text-zinc-200 rounded-bl-sm'
                    }`}>
                      {msg.role === 'admin' && (
                        <p className="text-emerald-200 text-[10px] font-bold mb-1">TÚ (RESPUESTA MANUAL)</p>
                      )}
                      <p>{msg.message}</p>
                      <p className={`text-xs mt-1.5 ${msg.role === 'user' ? 'text-indigo-300' : 'text-zinc-400'}`}>
                        {new Date(msg.timestamp).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Responder manualmente */}
            <div className="border-t border-zinc-800 p-4 flex-shrink-0 flex gap-2">
              <input
                className="flex-1 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-emerald-500"
                placeholder="Escribe una respuesta manual — se envía por WhatsApp real..."
                value={replyText}
                onChange={e => setReplyText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !sending) handleSendReply() }}
                disabled={sending}
              />
              <button
                onClick={handleSendReply}
                disabled={sending || !replyText.trim() || !selected}
                className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-medium px-4 py-2.5 rounded-xl transition-all flex-shrink-0"
              >
                <Send size={14} /> {sending ? 'Enviando...' : 'Enviar'}
              </button>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <MessageSquare size={40} className="text-zinc-700 mx-auto mb-3" />
              <p className="text-zinc-500 text-sm">Selecciona un usuario para ver su conversación</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}