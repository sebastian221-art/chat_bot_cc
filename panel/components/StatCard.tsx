// 📄 ARCHIVO: panel/components/StatCard.tsx
import { ReactNode } from 'react'

interface Props {
  label?:  string          // nombre original
  title?:  string          // alias — cualquiera de los dos sirve
  value:   string | number
  sub?:    string
  icon:    ReactNode
  color?:  'indigo' | 'emerald' | 'violet' | 'amber' | 'red' | 'blue'
  delay?:  number
}

const colorMap: Record<string, { bg: string; text: string; border: string }> = {
  indigo:  { bg: 'rgba(99,102,241,0.1)',  text: '#818cf8', border: 'rgba(99,102,241,0.2)'  },
  emerald: { bg: 'rgba(52,211,153,0.1)',  text: '#34d399', border: 'rgba(52,211,153,0.2)'  },
  violet:  { bg: 'rgba(167,139,250,0.1)', text: '#a78bfa', border: 'rgba(167,139,250,0.2)' },
  amber:   { bg: 'rgba(251,191,36,0.1)',  text: '#fbbf24', border: 'rgba(251,191,36,0.2)'  },
  red:     { bg: 'rgba(239,68,68,0.1)',   text: '#f87171', border: 'rgba(239,68,68,0.2)'   },
  blue:    { bg: 'rgba(59,130,246,0.1)',  text: '#60a5fa', border: 'rgba(59,130,246,0.2)'  },
}

export default function StatCard({ label, title, value, sub, icon, color = 'indigo', delay = 0 }: Props) {
  const heading = title ?? label ?? ''   // acepta ambos
  const c = colorMap[color] ?? colorMap.indigo

  return (
    <div
      className="animate-fade-up card-hover"
      style={{
        animationDelay:    `${delay}ms`,
        animationFillMode: 'both',
        background:        '#18181b',
        border:            '1px solid #27272a',
        borderRadius:      '16px',
        padding:           '20px',
      }}
    >
      <div className="flex items-start justify-between">
        <div>
          <p style={{ fontSize: '11px', color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>
            {heading}
          </p>
          <p style={{ fontSize: '30px', fontWeight: 800, color: '#fafafa', marginTop: '8px', lineHeight: 1 }}>
            {value}
          </p>
          {sub && (
            <p style={{ fontSize: '12px', color: '#a1a1aa', marginTop: '6px' }}>{sub}</p>
          )}
        </div>
        <div
          style={{
            width:          '40px',
            height:         '40px',
            borderRadius:   '10px',
            background:     c.bg,
            border:         `1px solid ${c.border}`,
            color:          c.text,
            display:        'flex',
            alignItems:     'center',
            justifyContent: 'center',
            flexShrink:     0,
          }}
        >
          {icon}
        </div>
      </div>
    </div>
  )
}