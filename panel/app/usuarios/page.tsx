'use client'
// 📄 ARCHIVO: panel/app/usuarios/page.tsx
import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { getUsers, createUser, updateUser, deleteUser, type AdminUser, type UserIn } from '@/lib/api'
import { logout } from '@/lib/auth'
import { UserPlus, Pencil, Trash2, X, Check, Shield, Store, Eye, EyeOff, RefreshCw, ArrowLeft, LogOut } from 'lucide-react'

const ROLES = [
  { value: 'admin',       label: 'Administrador',  desc: 'Acceso total' },
  { value: 'supervisor',  label: 'Supervisor CC',   desc: 'Dashboard, eventos, tiendas' },
  { value: 'local',       label: 'Dueño de local',  desc: 'Solo su panel de pedidos y menú' },
  { value: 'parqueadero', label: 'Parqueadero',      desc: 'Solo panel de parqueadero' },
]
const STORE_TYPES = [
  { value: 'restaurante', label: 'Restaurante' }, { value: 'tienda', label: 'Tienda / Ropa' },
  { value: 'farmacia', label: 'Farmacia' }, { value: 'cine', label: 'Cine' },
  { value: 'entretenimiento', label: 'Entretenimiento' },
]
const ROLE_COLORS: Record<string, string> = {
  admin: '#6366f1', supervisor: '#0ea5e9', local: '#10b981', parqueadero: '#f59e0b',
}
const BLANK: UserIn = { username: '', full_name: '', password: '', role: 'local', store_name: '', store_type: 'restaurante', store_id: '', is_active: true }

function slugify(s: string) {
  return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

export default function UsuariosPage() {
  const router = useRouter()
  const [users, setUsers]     = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [modal, setModal]     = useState<'create' | 'edit' | null>(null)
  const [editing, setEditing] = useState<AdminUser | null>(null)
  const [form, setForm]       = useState<UserIn>(BLANK)
  const [saving, setSaving]   = useState(false)
  const [formErr, setFormErr] = useState('')
  const [showPw, setShowPw]   = useState(false)
  const [deleting, setDeleting] = useState<AdminUser | null>(null)
  const [delLoad, setDelLoad]   = useState(false)

  const fetchUsers = useCallback(async () => {
    setLoading(true); setError('')
    try { setUsers(await getUsers()) }
    catch (e: unknown) { setError(e instanceof Error ? e.message : 'Error cargando usuarios') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchUsers() }, [fetchUsers])

  function openCreate() { setForm(BLANK); setFormErr(''); setShowPw(false); setEditing(null); setModal('create') }
  function openEdit(u: AdminUser) {
    setForm({ username: u.username, full_name: u.full_name, password: '', role: u.role, store_name: u.store_name || '', store_type: u.store_type || 'restaurante', store_id: u.store_id || '', is_active: u.is_active })
    setFormErr(''); setShowPw(false); setEditing(u); setModal('edit')
  }
  function closeModal() { setModal(null); setEditing(null) }

  function handleFormChange(field: keyof UserIn, value: string | boolean) {
    setForm(prev => {
      const next = { ...prev, [field]: value }
      if (field === 'store_name' && modal === 'create') next.store_id = slugify(value as string)
      return next
    })
  }

  async function handleSave() {
    setFormErr('')
    if (!form.username.trim()) return setFormErr('El nombre de usuario es obligatorio')
    if (modal === 'create' && !form.password) return setFormErr('La contraseña es obligatoria al crear')
    if (form.role === 'local' && !form.store_name?.trim()) return setFormErr('Debes indicar el nombre del local')
    setSaving(true)
    try {
      const payload: UserIn = { ...form,
        store_name: form.role === 'local' ? form.store_name : undefined,
        store_type: form.role === 'local' ? form.store_type : undefined,
        store_id:   form.role === 'local' ? form.store_id   : undefined,
      }
      if (modal === 'create') await createUser(payload)
      else if (editing) {
        const up: Partial<UserIn> = { ...payload }
        if (!up.password) delete up.password
        await updateUser(editing.id, up)
      }
      closeModal(); fetchUsers()
    } catch (e: unknown) { setFormErr(e instanceof Error ? e.message : 'Error guardando') }
    finally { setSaving(false) }
  }

  async function handleDelete() {
    if (!deleting) return
    setDelLoad(true)
    try { await deleteUser(deleting.id); setDeleting(null); fetchUsers() }
    catch (e: unknown) { alert(e instanceof Error ? e.message : 'Error eliminando') }
    finally { setDelLoad(false) }
  }

  function handleLogout() {
    if (confirm('¿Cerrar sesión?')) { logout(); router.push('/login') }
  }

  return (
    <div style={{ padding: '32px', maxWidth: 900, margin: '0 auto' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <button onClick={() => router.back()} style={btnIcon} title="Volver atrás">
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 style={{ color: '#fff', fontSize: 22, fontWeight: 700, margin: 0 }}>Gestión de usuarios</h1>
            <p style={{ color: '#71717a', fontSize: 13, marginTop: 4 }}>Controla quién accede al panel y qué puede ver</p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button onClick={fetchUsers} style={btnSecondary} title="Recargar"><RefreshCw size={14} /></button>
          <button onClick={openCreate} style={btnPrimary}><UserPlus size={15} /> Nuevo usuario</button>
          <div style={{ width: 1, height: 28, background: '#27272a' }} />
          <button onClick={handleLogout} style={{ ...btnSecondary, color: '#f87171', borderColor: '#7f1d1d44', gap: 6 }}>
            <LogOut size={14} /><span style={{ fontSize: 12 }}>Cerrar sesión</span>
          </button>
        </div>
      </div>

      {error && <div style={errorBox}>{error}</div>}

      {/* Tabla */}
      <div style={card}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 48, color: '#52525b' }}>Cargando usuarios...</div>
        ) : users.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 48, color: '#52525b' }}>Sin usuarios registrados</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr>{['Usuario', 'Nombre', 'Rol', 'Local', 'Estado', ''].map(h => <th key={h} style={thS}>{h}</th>)}</tr></thead>
            <tbody>
              {users.map((u, i) => (
                <tr key={u.id} style={{ background: i % 2 === 0 ? 'transparent' : '#ffffff04' }}>
                  <td style={tdS}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ width: 32, height: 32, borderRadius: '50%', background: ROLE_COLORS[u.role] || '#6366f1', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 700, fontSize: 13 }}>
                        {(u.full_name || u.username).charAt(0).toUpperCase()}
                      </div>
                      <span style={{ color: '#e4e4e7', fontWeight: 500, fontSize: 13 }}>{u.username}</span>
                    </div>
                  </td>
                  <td style={tdS}><span style={{ color: '#a1a1aa', fontSize: 13 }}>{u.full_name || '—'}</span></td>
                  <td style={tdS}>
                    <span style={{ background: (ROLE_COLORS[u.role] || '#6366f1') + '22', color: ROLE_COLORS[u.role] || '#6366f1', border: `1px solid ${(ROLE_COLORS[u.role] || '#6366f1')}44`, borderRadius: 6, padding: '2px 9px', fontSize: 11, fontWeight: 600 }}>
                      {u.role_label}
                    </span>
                  </td>
                  <td style={tdS}>
                    {u.store_name
                      ? <span style={{ color: '#a1a1aa', fontSize: 12, display: 'flex', alignItems: 'center', gap: 5 }}><Store size={11} />{u.store_name}<span style={{ color: '#3f3f46' }}>· {u.store_type}</span></span>
                      : <span style={{ color: '#3f3f46', fontSize: 12 }}>—</span>}
                  </td>
                  <td style={tdS}>
                    <span style={{ background: u.is_active ? '#052e1644' : '#1c0a0a44', color: u.is_active ? '#34d399' : '#f87171', border: `1px solid ${u.is_active ? '#34d39944' : '#f8717144'}`, borderRadius: 6, padding: '2px 9px', fontSize: 11, fontWeight: 600 }}>
                      {u.is_active ? 'Activo' : 'Inactivo'}
                    </span>
                  </td>
                  <td style={{ ...tdS, textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <button onClick={() => openEdit(u)} style={btnIcon} title="Editar"><Pencil size={13} /></button>
                      <button onClick={() => setDeleting(u)} style={{ ...btnIcon, color: '#f87171' }} title="Eliminar"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modal crear/editar */}
      {modal && (
        <div style={overlay} onClick={e => e.target === e.currentTarget && closeModal()}>
          <div style={modalBox}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
              <h2 style={{ color: '#fff', fontSize: 16, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Shield size={16} style={{ color: '#6366f1' }} />
                {modal === 'create' ? 'Nuevo usuario' : `Editar · ${editing?.username}`}
              </h2>
              <button onClick={closeModal} style={btnIcon}><X size={16} /></button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                <Field label="Usuario *">
                  <input value={form.username} onChange={e => handleFormChange('username', e.target.value)} placeholder="ej: corral_admin" disabled={modal === 'edit'} style={{ ...inputSt, opacity: modal === 'edit' ? 0.5 : 1 }} />
                </Field>
                <Field label="Nombre completo">
                  <input value={form.full_name || ''} onChange={e => handleFormChange('full_name', e.target.value)} placeholder="ej: Juan García" style={inputSt} />
                </Field>
              </div>
              <Field label={modal === 'edit' ? 'Nueva contraseña (vacío = no cambiar)' : 'Contraseña *'}>
                <div style={{ position: 'relative' }}>
                  <input type={showPw ? 'text' : 'password'} value={form.password} onChange={e => handleFormChange('password', e.target.value)} placeholder="••••••••" style={{ ...inputSt, paddingRight: 38 }} />
                  <button type="button" onClick={() => setShowPw(v => !v)} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#71717a' }}>
                    {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </Field>
              <Field label="Rol *">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  {ROLES.map(r => (
                    <button key={r.value} type="button" onClick={() => handleFormChange('role', r.value)}
                      style={{ padding: '8px 12px', borderRadius: 8, cursor: 'pointer', textAlign: 'left', border: `1px solid ${form.role === r.value ? ROLE_COLORS[r.value] : '#27272a'}`, background: form.role === r.value ? ROLE_COLORS[r.value] + '22' : 'transparent', color: form.role === r.value ? ROLE_COLORS[r.value] : '#71717a' }}>
                      <div style={{ fontWeight: 600, fontSize: 12 }}>{r.label}</div>
                      <div style={{ fontSize: 10, opacity: 0.7, marginTop: 2 }}>{r.desc}</div>
                    </button>
                  ))}
                </div>
              </Field>
              {form.role === 'local' && (
                <div style={{ background: '#0c0c0e', border: '1px solid #27272a', borderRadius: 10, padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <p style={{ color: '#6366f1', fontSize: 11, fontWeight: 600, margin: 0, textTransform: 'uppercase' }}>Configuración del local</p>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <Field label="Nombre del local *">
                      <input value={form.store_name || ''} onChange={e => handleFormChange('store_name', e.target.value)} placeholder="ej: El Corral" style={inputSt} />
                    </Field>
                    <Field label="Tipo de local">
                      <select value={form.store_type || 'restaurante'} onChange={e => handleFormChange('store_type', e.target.value)} style={inputSt}>
                        {STORE_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                      </select>
                    </Field>
                  </div>
                  <Field label="ID de URL (auto-generado, editable)">
                    <input value={form.store_id || ''} onChange={e => handleFormChange('store_id', e.target.value)} placeholder="ej: el-corral" style={inputSt} />
                    <p style={{ color: '#52525b', fontSize: 10, marginTop: 4 }}>Accede a: /panel/{form.store_type || 'restaurante'}/{form.store_id || '...'}</p>
                  </Field>
                </div>
              )}
              {modal === 'edit' && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <button type="button" onClick={() => handleFormChange('is_active', !form.is_active)}
                    style={{ width: 36, height: 20, borderRadius: 10, border: 'none', cursor: 'pointer', background: form.is_active ? '#6366f1' : '#3f3f46', position: 'relative' }}>
                    <span style={{ position: 'absolute', top: 2, left: form.is_active ? 18 : 2, width: 16, height: 16, borderRadius: '50%', background: '#fff', transition: 'left .2s' }} />
                  </button>
                  <span style={{ color: form.is_active ? '#a1a1aa' : '#52525b', fontSize: 13 }}>Usuario {form.is_active ? 'activo' : 'inactivo'}</span>
                </div>
              )}
              {formErr && <div style={errorBox}>{formErr}</div>}
              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', paddingTop: 4 }}>
                <button onClick={closeModal} style={btnSecondary} disabled={saving}>Cancelar</button>
                <button onClick={handleSave} style={btnPrimary} disabled={saving}>
                  <Check size={14} />{saving ? 'Guardando...' : modal === 'create' ? 'Crear usuario' : 'Guardar cambios'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Confirm delete */}
      {deleting && (
        <div style={overlay} onClick={e => e.target === e.currentTarget && setDeleting(null)}>
          <div style={{ ...modalBox, maxWidth: 380 }}>
            <div style={{ textAlign: 'center', padding: '8px 0' }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>🗑️</div>
              <h3 style={{ color: '#fff', fontSize: 16, fontWeight: 700, margin: '0 0 8px' }}>¿Eliminar usuario?</h3>
              <p style={{ color: '#71717a', fontSize: 13, margin: '0 0 24px' }}>
                <strong style={{ color: '#a1a1aa' }}>{deleting.username}</strong> perderá acceso al panel inmediatamente.
              </p>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
                <button onClick={() => setDeleting(null)} style={btnSecondary} disabled={delLoad}>Cancelar</button>
                <button onClick={handleDelete} disabled={delLoad} style={{ ...btnPrimary, background: '#dc2626' }}>
                  <Trash2 size={14} />{delLoad ? 'Eliminando...' : 'Sí, eliminar'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ display: 'block', color: '#a1a1aa', fontSize: 11, fontWeight: 600, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</label>
      {children}
    </div>
  )
}

const card:         React.CSSProperties = { background: '#18181b', border: '1px solid #27272a', borderRadius: 14, overflow: 'hidden' }
const thS:          React.CSSProperties = { padding: '12px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#52525b', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #27272a' }
const tdS:          React.CSSProperties = { padding: '12px 16px', borderBottom: '1px solid #1a1a1d' }
const overlay:      React.CSSProperties = { position: 'fixed', inset: 0, background: '#00000088', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 24 }
const modalBox:     React.CSSProperties = { background: '#18181b', border: '1px solid #27272a', borderRadius: 16, padding: '28px', width: '100%', maxWidth: 560, maxHeight: '90vh', overflowY: 'auto' }
const inputSt:      React.CSSProperties = { width: '100%', padding: '9px 12px', background: '#09090b', border: '1px solid #27272a', borderRadius: 8, color: '#fff', fontSize: 13, outline: 'none', boxSizing: 'border-box' }
const btnPrimary:   React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 7, padding: '9px 18px', borderRadius: 9, border: 'none', background: '#6366f1', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer' }
const btnSecondary: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 7, padding: '9px 18px', borderRadius: 9, border: '1px solid #27272a', background: 'transparent', color: '#a1a1aa', fontSize: 13, fontWeight: 600, cursor: 'pointer' }
const btnIcon:      React.CSSProperties = { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30, borderRadius: 7, border: '1px solid #27272a', background: 'transparent', color: '#71717a', cursor: 'pointer' }
const errorBox:     React.CSSProperties = { background: '#3f1212', border: '1px solid #7f1d1d', borderRadius: 8, padding: '10px 14px', color: '#fca5a5', fontSize: 13 }