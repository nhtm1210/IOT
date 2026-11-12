import type { ReactNode } from 'react'
import { AlertCircle, ArrowRight, LoaderCircle, WifiOff } from 'lucide-react'

export function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{description ? <p className="page-description">{description}</p> : null}</div>{action ? <div className="heading-action">{action}</div> : null}</div>
}

export function Panel({ title, subtitle, action, children, className = '' }: { title?: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><div className="panel-heading">{title ? <div><h2>{title}</h2>{subtitle ? <p>{subtitle}</p> : null}</div> : <span />}{action}</div>{children}</section>
}

export function Badge({ tone = 'neutral', children }: { tone?: 'success' | 'warning' | 'danger' | 'neutral' | 'info'; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

export function StateBadge({ online, labels = ['Online', 'Offline'] }: { online: boolean; labels?: [string, string] }) {
  return <Badge tone={online ? 'success' : 'neutral'}><span className="badge-dot" />{online ? labels[0] : labels[1]}</Badge>
}

export function Loading({ label = 'Đang tải dữ liệu...' }: { label?: string }) {
  return <div className="empty-block"><LoaderCircle size={22} className="spin" /><span>{label}</span></div>
}

export function Empty({ title = 'Chưa có dữ liệu', description }: { title?: string; description?: string }) {
  return <div className="empty-block"><WifiOff size={22} /><strong>{title}</strong>{description ? <span>{description}</span> : null}</div>
}

export function InlineError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="inline-error"><AlertCircle size={18} /><span>{message}</span>{onRetry ? <button type="button" onClick={onRetry}>Thử lại <ArrowRight size={14} /></button> : null}</div>
}

export function Toggle({ checked, onChange, disabled = false, label }: { checked: boolean; onChange: (value: boolean) => void; disabled?: boolean; label: string }) {
  return <button type="button" role="switch" aria-checked={checked} aria-label={label} className={`toggle ${checked ? 'is-on' : ''}`} disabled={disabled} onClick={() => onChange(!checked)}><span /></button>
}

export function Metric({ label, value, unit, icon, hint, tone = 'default' }: { label: string; value: string | number; unit?: string; icon: ReactNode; hint?: string; tone?: 'default' | 'warning' | 'danger' }) {
  return <div className={`metric metric-${tone}`}><div className="metric-top"><span>{label}</span><span className="metric-icon">{icon}</span></div><div className="metric-value">{value}<small>{unit}</small></div><p>{hint || '\u00a0'}</p></div>
}
