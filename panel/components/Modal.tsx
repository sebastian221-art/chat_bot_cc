// 📄 ARCHIVO: panel/components/Modal.tsx
'use client'
import { useEffect } from 'react'
import { X } from 'lucide-react'

interface Props {
  open:     boolean           // ← prop que faltaba
  title:    string
  onClose:  () => void
  children: React.ReactNode
  size?:    'sm' | 'md' | 'lg'
}

const sizes = { sm: '440px', md: '560px', lg: '720px' }

export default function Modal({ open, title, onClose, children, size = 'md' }: Props) {
  // Cerrar con ESC y bloquear scroll mientras está abierto
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handler)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  // Si no está abierto no renderiza nada
  if (!open) return null

  return (
    <div
      className="animate-fade-up"
      style={{
        position:       'fixed',
        inset:          0,
        zIndex:         100,
        display:        'flex',
        alignItems:     'center',
        justifyContent: 'center',
        padding:        '16px',
      }}
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position:       'absolute',
          inset:          0,
          background:     'rgba(0,0,0,0.75)',
          backdropFilter: 'blur(4px)',
        }}
      />

      {/* Dialog */}
      <div
        style={{
          position:        'relative',
          width:           '100%',
          maxWidth:        sizes[size],
          background:      '#18181b',
          border:          '1px solid #27272a',
          borderRadius:    '16px',
          boxShadow:       '0 24px 80px rgba(0,0,0,0.7)',
          maxHeight:       '90vh',
          display:         'flex',
          flexDirection:   'column',
        }}
      >
        {/* Header */}
        <div
          style={{
            display:         'flex',
            alignItems:      'center',
            justifyContent:  'space-between',
            padding:         '18px 24px',
            borderBottom:    '1px solid #27272a',
            flexShrink:      0,
          }}
        >
          <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#fafafa' }}>
            {title}
          </h2>
          <button
            onClick={onClose}
            style={{
              width:           '30px',
              height:          '30px',
              borderRadius:    '8px',
              background:      '#27272a',
              border:          '1px solid #3f3f46',
              cursor:          'pointer',
              display:         'flex',
              alignItems:      'center',
              justifyContent:  'center',
              color:           '#a1a1aa',
              transition:      'all 0.15s',
            }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '24px', overflowY: 'auto' }}>
          {children}
        </div>
      </div>
    </div>
  )
}