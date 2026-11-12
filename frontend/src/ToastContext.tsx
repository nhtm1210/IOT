import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { X } from 'lucide-react'

type Tone = 'success' | 'error' | 'info'
interface Notice { id: number; message: string; tone: Tone }
const ToastContext = createContext<(message: string, tone?: Tone) => void>(() => undefined)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [notices, setNotices] = useState<Notice[]>([])

  const notify = useCallback((message: string, tone: Tone = 'info') => {
    const id = Date.now() + Math.random()
    setNotices((current) => [...current.slice(-3), { id, message, tone }])
    window.setTimeout(() => setNotices((current) => current.filter((notice) => notice.id !== id)), 6000)
  }, [])

  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {notices.map((notice) => (
          <div className={`toast toast-${notice.tone}`} key={notice.id}>
            <span>{notice.message}</span>
            <button className="icon-button" aria-label="Đóng thông báo" onClick={() => setNotices((current) => current.filter((item) => item.id !== notice.id))}><X size={16} /></button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
